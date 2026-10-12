from typing import Any , TypeVar , List

T = TypeVar('T')

def get_first_any(items: List[Any]) -> Any:
    return items[0]

def get_second_T(items: List[T]) -> T:
    return items[1]


if __name__ == '__main__':
    names = ["alice" , "bob"]
    res_any = get_first_any(names)
    print(res_any)

    res_gen = get_second_T(names)
    print(res_gen)





