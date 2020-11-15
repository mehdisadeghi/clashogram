FROM frolvlad/alpine-python3
RUN pip --no-cache-dir install --no-compile clashogram

ENV LC_ALL=C.UTF-8
WORKDIR /app
CMD ["clashogram"]
EXPOSE 3000


