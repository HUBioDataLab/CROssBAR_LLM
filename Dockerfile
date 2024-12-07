FROM python:3.10-slim-bookworm

RUN apt update
RUN apt upgrade -y

# Install node
RUN apt install -y nodejs wget

# Install pnpm
RUN wget -qO- https://get.pnpm.io/install.sh | ENV="$HOME/.bashrc" SHELL="$(which bash)" bash -

# Install static-web-server
RUN curl --proto '=https' --tlsv1.2 -sSfL https://get.static-web-server.net | sh

# Install backend requirements
WORKDIR ..
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN pip install "uvicorn[standard]"
RUN rm -f requirements.txt

# Copy source
COPY crossbar_llm crossbar_llm
WORKDIR crossbar_llm

# Install & build frontend
WORKDIR frontend
RUN /root/.local/share/pnpm/pnpm install
RUN /root/.local/share/pnpm/pnpm build
RUN cp -rf build /public
WORKDIR ..
RUN rm -rf frontend

WORKDIR ..
COPY startup.sh .
RUN chmod +x startup.sh

EXPOSE 8000
EXPOSE 8501

ENTRYPOINT ["./startup.sh"]
