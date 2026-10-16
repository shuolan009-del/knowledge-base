# processor/import_processor/nodes/node_md_img.py
import base64
import json
import logging
import os
import re
import time
from collections import deque
from pathlib import Path
from typing import Tuple, List, Deque, Dict

from langchain_openai import ChatOpenAI

from config.lm_config import lm_config
from config.storage_config import storage_config
from processor.import_processor.base import BaseNode, setup_logging
from processor.import_processor.exceptions import StateFieldError, FileProcessingError
from processor.import_processor.state import ImportGraphState
from utils.storage_utils import clean_dir, save_file

#  分发节点 + PDF转MD节点  +  MD解析节点
class NodeMDImg(BaseNode):
    """
    MarkDown图片处理节点：多模态图片理解
    """

    name = "node_md_img"

    def process(self, state: ImportGraphState):

        """
        MD文件图片处理核心节点
        核心流程：
        1. 获取MD内容、文件路径、图片文件夹路径
        2. 扫描图片文件夹，筛选MD中实际引用的支持格式图片
        3. 调用多模态大模型为图片生成内容摘要
        4. 将图片复制到本地存储，替换MD中本地图片路径为存储访问URL，并填充图片摘要
        5. 备份原MD文件，保存处理后的新MD文件并更新状态

        :param state: md_path、md_content
        :return: md_path、md_content
        """

        # 步骤1：初始化数据，获取MD核心信息
        md_content, md_path_obj, images_dir = self._step_1_get_content(state)
        # 修复：无论是否存在图片，都先把 MD 内容写回 state，
        # 否则无图片文件夹时会直接 return，导致后续 node_document_split 取到空内容而报错
        state["md_content"] = md_content
        if not images_dir.exists():
            self.logger.info("无图片文件夹，跳过图片处理")
            return state

        # 步骤2：扫描并筛选MD中引用的图片
        target_images = self._step_2_scan_images(md_content, images_dir)
        if not target_images:
            self.logger.info("未检测到MD中引用了图片，跳过图片处理")
            return state

        # 步骤3：调用多模态大模型生成图片摘要
        summaries = self._step_3_generate_summaries(md_path_obj.stem, target_images)
        print(summaries)
        # 步骤4：将图片复制到本地存储，替换MD图片路径并填充摘要
        new_md_content = self._step_4_upload_and_replace(md_path_obj.stem, target_images, summaries, md_content)

        # 步骤5：备份并保存新MD文件
        # new_md_content 已经 最新的了 ![摘要](云上的地址)
        new_md_file_name = self._step_5_backup_new_md_file(state['md_path'], new_md_content)

        # 步骤6：更新state状态值
        state["md_content"] = new_md_content
        state["md_path"] = new_md_file_name

        return state

    def _step_5_backup_new_md_file(self, origin_md_path: str, md_content: str) -> str:
        """
        步骤5：将处理后的MD内容保存为新文件（原文件不变，避免数据丢失）
        新文件命名规则：原文件名 + _new.md（如test.md → test_new.md）
        :param origin_md_path: 原始MD文件完整路径
        :param md_content: 处理后的新MD内容
        :return: 新MD文件的完整路径
        """

        new_md_file_name = os.path.splitext(origin_md_path)[0] + "_new.md"
        with open(new_md_file_name, "w", encoding="utf-8") as f:
            f.write(md_content)

        return new_md_file_name

    def _step_4_upload_and_replace(
            self,
            doc_stem: str,
            target_images: List[Tuple[str, str, Tuple[str, str]]],
            summaries: Dict[str, str],
            md_content: str
    ) -> str:
        """
        步骤 4: 上传图片并合并信息，然后替换 Markdown 中的内容。

        流程：
        1. 确定本地存储的上传目录（按文档名隔离）。
        2. 清理该目录下的旧数据。
        3. 批量保存图片。
        4. 合并“图片摘要”和“图片URL”。
        5. 替换 Markdown 文本中的图片引用。
        :param doc_stem: 文档文件名（不含后缀），作为存储子目录名（按文档隔离）
        :param target_images: 待处理图片列表，元素为(图片文件名, 图片完整路径, 图片上下文)
        :param summaries: 图片摘要字典，键：图片文件名，值：内容摘要
        :param md_content: 原始MD文件内容
        :return: 图片引用替换后的新MD内容
        """

        # 1. 获取图片上传路径（存储内相对目录）
        upload_dir = f"{storage_config.img_dir}/{doc_stem}".replace(" ", "")

        # 2. 清理已有目录
        self._clean_storage_dir(upload_dir)

        # 3. 批量上传
        urls = self._upload_images_batch(upload_dir, target_images)

        # 4. 合并图片摘要和URL，过滤上传失败的图片
        image_info = self._merge_summary_and_url(summaries, urls)

        # 5. 替换MD中的图片引用
        md_content = self._process_md_file(md_content, image_info)

        return md_content

    def _process_md_file(self, md_content: str, image_info: Dict[str, Tuple[str, str]]) -> str:
        """
        核心功能：替换MD内容中的本地图片引用为存储访问URL
        替换规则：![原描述](本地路径) → ![图片摘要](存储URL)
        :param md_content: 原始MD文件内容
        :param image_info: 合并后的图片信息字典，键：图片文件名，值：(摘要, URL)
        :return: 替换后的新MD内容
        """

        for image_file, (summary, new_url) in image_info.items():
            pattern = re.compile(r"!\[.*?\]\(.*?" + re.escape(image_file) + r".*?\)")
            #sub(替换规则, 将要被替换的内容
            md_content = pattern.sub(lambda m: f"![{summary}]({new_url})", md_content)

        return md_content

    def _merge_summary_and_url(self, summaries: Dict[str, str], urls: Dict[str, str]) -> Dict[str, Tuple[str, str]]:
        """
        合并图片摘要字典和URL字典，过滤掉上传失败无URL的图片
        :param summaries: 图片摘要字典，键：图片文件名，值：内容摘要
        :param urls: 图片URL字典，键：图片文件名，值：存储访问URL
        :return: 合并后的图片信息字典，键：图片文件名，值：(摘要, URL)元组
        """
        image_info = {}
        for image_file, summary in summaries.items():
            if url := urls.get(image_file):# 海象运算符
                image_info[image_file] = (summary, url)
        return image_info

    def _upload_images_batch(self, upload_dir: str, target_images: List[Tuple]) -> Dict[str, str]:
        """
        批量保存待处理图片至本地存储，返回图片文件名与访问URL的映射关系
        :param upload_dir: 存储内上传目录
        :param target_images: 待处理图片列表，元素为(图片文件名, 图片完整路径, 图片上下文)
        :return: 图片URL字典，键：图片文件名，值：访问URL
        """
        urls = {}
        for img_file, img_path, _ in target_images:
            object_name = f"{upload_dir}/{img_file}"
            urls[img_file] = self._upload_image(img_path, object_name)
        return urls

    def _upload_image(self, local_path: str, object_name: str) -> str | None:
        """
        将单张本地图片复制到本地存储目录，并返回访问URL
        :param local_path: 图片本地完整路径
        :param object_name: 存储内相对路径
        :return: 图片访问URL（保存失败返回None）
        """

        try:
            url = save_file(local_path, object_name)
            if url is None:
                self.logger.error(f"保存图片失败：{local_path}")
            return url
        except Exception as e:
            self.logger.error(f"保存图片失败：{local_path}，错误：{e}")
            return None

    def _clean_storage_dir(self, update_dir: str) -> None:
        """按文档维度清理存储子目录（对应原 MinIO 旧图清理）"""
        try:
            clean_dir(update_dir)
        except Exception as e:
            self.logger.error(f"清理图片目录失败，错误原因：{e}")

    def _step_3_generate_summaries(self, doc_stem: str, target_images: List[Tuple[str, str, Tuple[str, str]]]) -> Dict[str, str]:
        """
        步骤3：批量为待处理图片生成内容摘要，带API速率限制防止触发大模型限流
        :param doc_stem: 文档文件名（不含后缀），作为大模型prompt上下文
        :param targets: 待处理图片列表，元素为(图片文件名, 图片完整路径, 图片上下文)
        :param requests_per_minute: 每分钟最大API请求数，默认9次（按大模型限制调整）
        :return: 图片摘要字典，键：图片文件名，值：图片内容摘要
        """

        # 1. 定义摘要
        summaries = {}

        # 2. 定义双端队列
        request_deque = deque()

        # 3. 循环处理图片
        for img_file, img_path, context in target_images:

            # 3.1 限速
            self._apply_api_rate_limit(request_deque, 10,window_seconds=10 )

            # 3.2 向模型发送请求
            summaries[img_file] = self._summarize_image(img_path, root_folder=doc_stem, image_content=context)

        return summaries

    def _summarize_image(self, image_path: str, root_folder: str, image_content: Tuple[str, str]) -> str:
        """
           调用多模态大模型总结图片内容。

           参数：
           - image_path: 图片本地路径。
           - root_folder: 文档所属文件夹名（提供更多上下文）。
           - image_content: 图片在文档中的上下文 (前文, 后文)。
        """

        # 1. 将图片转换成base64
        with open(image_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode("utf-8")


        try:
            chat_model = ChatOpenAI(
                model=lm_config.vl_model,
                api_key=lm_config.api_key,
                base_url=lm_config.base_url,
                temperature=lm_config.llm_temperature
            )

            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"""这是"{root_folder}"文件中的一张图片，图片上文部分为"{image_content[0]}"，下文部分为"{image_content[1]}"，请用中文简要总结这张图片的内容，用于 Markdown 图片标题。"""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ]

            response = chat_model.invoke(messages)
            return response.content.strip().replace("\n","")

        except Exception as e:
            self.logger.error(f"获取图片摘要失败:{image_path}， 错误：{e}")
            return root_folder


    def _apply_api_rate_limit(
            self,
            request_times: Deque[float],
            max_requests: int,
            window_seconds: int = 60
    ) -> None:
        """
        通用滑动窗口API速率限制器（抽离为公共工具）
        核心逻辑：维护请求时间戳双端队列，窗口内请求数超上限则自动等待，防止触发第三方API限流
        :param request_times: 存储请求时间戳的双端队列，需外部初始化（全局/单例），跨调用复用
        :param max_requests: 速率限制窗口内的最大允许请求次数
        :param window_seconds: 速率限制滑动窗口时长，默认60秒（1分钟）
        :return: None，超出限制时会阻塞等待
        """
        # 1. 记录当前时间
        current_time = time.time()

        # 2. 清理滑动窗口中的过期请求
        while request_times and current_time - request_times[0] >= window_seconds:
            request_times.popleft()

        # 3. 窗口内请求数达到上限，计算需要等待的时间并阻塞
        if len(request_times) >= max_requests:
            #计算需要等待的时长 = 窗口的总时长 - 窗口内第一个请求的时间
            sleep_duration = window_seconds - (current_time - request_times[0])
            if sleep_duration > 0:
                self.logger.info(f"请求被限速，等待{sleep_duration:.2f}秒...")

                #等。。。。
                time.sleep(sleep_duration)

                #等完了
                current_time = time.time()
                while request_times and current_time - request_times[0] >= window_seconds:
                    request_times.popleft()

        # 4. 记录当前请求的时间戳，新请求入队
        request_times.append(current_time)
        self.logger.info(f"{self.name} 请求成功，当前{window_seconds}s窗口内请求次数为{len(request_times)}")



    def _step_2_scan_images(self, md_content: str, images_dir: Path) -> List[Tuple[str, str, Tuple[str, str]]]:
        """
        扫描图片文件夹，过滤出「支持格式+MD中实际引用」的图片，组装处理元数据
        :param md_content: MD文件完整内容
        :param images_dir: 图片文件夹路径对象
        :return: 待处理图片列表，每个元素为(图片文件名, 图片完整路径, 图片上下文)元组
        """

        target_images = []
        # 对图片文件夹进行遍历
        for image_file in os.listdir(images_dir):
            # 1. 过滤无效后缀
            file_ext = os.path.splitext(image_file)[1].lower()
            # 和合法后缀进行比较
            if file_ext not in self.config.image_extensions:
                self.logger.warning(f"图片{image_file}格式不支持")
                continue

            # 2. 组装图片的完整路径并转成字符串
            img_path = str(images_dir / image_file)

            # 3. 查找这个图片在md文档中引用的上下文
            context = self._find_image_in_md(md_content, image_file)

            if not context:
                self.logger.warning(f"图片{image_file}未在md文档中找到")
                continue

            # 4. 将查询到的图片组装到列表中
            target_images.append((image_file, img_path, context))

        return target_images

    def _step_1_get_content(self, state: ImportGraphState) -> Tuple[str, Path, Path]:
        """
        从全局状态中提取并初始化MD处理所需核心数据
        :param state: 流程全局状态对象
        :return: 元组(MD文件内容, MD文件路径, 图片文件夹路径)
        :raise FileProcessingError: 当状态中无有效MD文件路径时抛出
        """

        # 1. 参数非空校验
        md_path = state.get("md_path")
        if not md_path:
            raise StateFieldError(
                field_name="md_path",
                message="MD文件路径不能为空",
                expected_type=str)

        # 2. 路径转换
        md_path_obj = Path(md_path)

        # 3. 检查文件的有效性
        if not md_path_obj.exists():
            raise FileProcessingError(message=f"文件{md_path_obj.name}不存在")

        # 4. 获取md_content
        md_content = md_path_obj.read_text(encoding="utf-8")

        # 5. 获取md文件的图片文件夹路径
        img_dir = md_path_obj.parent / "images"

        return md_content, md_path_obj, img_dir

    def _find_image_in_md(
            self,
            md_content: str,  # md文件的完整内容
            image_file: str,  # 图片文件
            context_len: int = 100) -> Tuple[str, str]:

        # re.escape ： 给我将参数中的特殊符号进行转义
        # r：不要给我转义
        # 1 定义正则表达式
        #  ![](images/ac26d5ab3a9f599eb2f58c2f2cb89f009fd2172b49782804756ea10c7256d4b4.jpg)
        pattern = re.compile(r"!\[.*?\]\(.*?" + re.escape(image_file) + r".*?\)")
        match = pattern.search(md_content)
        if not match:
            # 没有找到图片
            return None

        # 2 截取图片前后的上文和下文
        start, end = match.span()
        # print(f"start =  {start}")
        # print(f"end =  {end}")
        pre_text = md_content[max(0, start - context_len):start]
        post_text = md_content[end:min(len(md_content), end + context_len)]

        # 3 返回图片的前文和后文
        return pre_text, post_text


if __name__ == "__main__":
    setup_logging()

    md_path = r"D:\output\hak180产品安全手册\hak180产品安全手册.md"
    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    init_state = {
        "md_path": md_path,
        "md_content": md_content
    }

    # 执行核心处理流程
    node_md_img = NodeMDImg()
    result = node_md_img(init_state)

    logging.getLogger().info(json.dumps(result, ensure_ascii=False, indent=4))
