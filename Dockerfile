FROM frolvlad/alpine-python3
RUN pip --no-cache-dir install --upgrade --no-compile flit

ENV FLIT_ROOT_INSTALL=1
WORKDIR /app

ADD pyproject.toml .
ADD LICENSE.txt .
ADD README.rst .
ADD clashogram ./clashogram
RUN flit install

ENV LC_ALL=C.UTF-8
WORKDIR /app
ENTRYPOINT ["clashogram"]


