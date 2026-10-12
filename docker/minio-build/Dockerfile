FROM alpine:latest
COPY minio /usr/bin/minio
RUN chmod +x /usr/bin/minio
EXPOSE 9000 9001
ENTRYPOINT ["/usr/bin/minio"]
