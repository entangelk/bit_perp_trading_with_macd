FROM python:3.10.7

# OpenJDK 설치
RUN apt-get update && \
    apt-get install -y openjdk-17-jdk fonts-nanum && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Chrome and related dependencies
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - && \
    echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | tee /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && apt-get install -y google-chrome-stable && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# JAVA_HOME 환경 변수 설정
ENV JAVA_HOME /usr/lib/jvm/java-17-openjdk-amd64

# 작업 디렉토리 설정
WORKDIR /app

ARG BRANCH_NAME=trading_bot
ARG DIR_NAME=trading_bot

# tmp 디렉토리 생성 및 권한 설정
RUN mkdir -p /tmp && chmod 777 /tmp

# Clone the Git repository
RUN git clone https://github.com/entangelk/bit_perp_trading_with_macd ${DIR_NAME}

# Change working directory
WORKDIR /app/${DIR_NAME}

# Install requirements
RUN pip install --no-cache-dir -r requirements.txt