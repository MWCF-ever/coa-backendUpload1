############# build arguments #############
ARG PYTHON_IMAGE=python:3.11.4-slim
ARG TARGET=prod            # dev 或 prod，外部可覆盖：docker build --build-arg TARGET=dev …

############# common-stage #############
FROM ${PYTHON_IMAGE} AS common-stage

# ---- 基础用户 / 目录 ----
ARG UID=1000
ARG USER=appuser
ENV USER=${USER}
RUN useradd --home-dir /home/${USER} --create-home --uid ${UID} --user-group ${USER}

ARG WORKDIR=/app
WORKDIR ${WORKDIR}

# ---- 拷贝依赖清单 & 基础目录 ----
COPY requirements.txt .

# ---- 创建必要目录并设置权限 ----
RUN mkdir -p logs uploads uploads/pdfs certs && \
    chmod 777 logs uploads uploads/pdfs

############# build-stage #############
# 把源码预编译成 .pyc，加速生产镜像启动并隐藏源码
FROM ${PYTHON_IMAGE} AS build-stage
WORKDIR /src
COPY . .
RUN echo "⏳  byte-compiling sources…" && \
    python -m compileall -f -j 0 app/

############# prod-stage #############
FROM common-stage AS prod-stage

# ---------- 安装系统依赖（PDF处理需要）----------
USER root
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        libfreetype6-dev \
        libjpeg62-turbo-dev \
        libmupdf-dev \
        mupdf-tools && \
    rm -rf /var/lib/apt/lists/*

# ---------- 安装生产依赖 ----------
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && rm -rf ~/.cache

# ---------- 拷贝编译后的代码 ----------
COPY --from=build-stage /src/app /app/app
COPY --from=build-stage /src/alembic /app/alembic
COPY --from=build-stage /src/alembic.ini /app/
COPY --from=build-stage /src/run.py /app/
COPY --from=build-stage /src/.env.example /app/

# ---------- 重要：拷贝测试 PDF 文件 ----------
# 如果有测试 PDF 文件，确保它们被包含
COPY --from=build-stage /src/uploads /app/uploads

# 或者，如果你有专门的测试数据目录
# COPY --from=build-stage /src/test_data /app/test_data

# ---------- 运行环境变量 ----------
ENV PYTHONPATH=/app
ENV UVICORN_HOST="0.0.0.0"
ENV UVICORN_PORT="8000"
ENV SSL_ENABLED="False"
ENV DEBUG="False"
EXPOSE ${UVICORN_PORT}

# ---------- 健康检查 ----------
HEALTHCHECK --start-period=60s --interval=30s --timeout=5s --retries=3 CMD \
  curl --fail --silent --max-time 3 "http://localhost:${UVICORN_PORT}/api/health" >/dev/null || exit 1

# ---------- 最终以非 root 身份运行 ----------
USER ${USER}
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

############# dev-stage #############
FROM common-stage AS dev-stage

# ---- 额外系统包（调试、编译、PDF 字体支持等）----
USER root
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        curl \
        gcc \
        build-essential \
        libxml2-dev \
        libxslt1-dev \
        libfreetype6-dev \
        libjpeg62-turbo-dev \
        libmupdf-dev \
        mupdf-tools \
        vim \
        postgresql-client && \
    rm -rf /var/lib/apt/lists/*

# ---- python 依赖 ----
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir pytest-cov ipython jupyter && \
    rm -rf ~/.cache

# ---- 拷贝源码（开发态需要原始代码和测试文件）----
USER ${USER}
COPY . /app

# ---- 确保测试 PDF 文件在开发环境中可用 ----
# 在开发环境中，所有文件都会被拷贝，包括 uploads 目录

ENV PYTHONPATH=/app
ENV DEBUG="True"
ENV SSL_ENABLED="False"
EXPOSE 8000

# 开发模式启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

############# 选择最终 stage #############
FROM ${TARGET}-stage AS final