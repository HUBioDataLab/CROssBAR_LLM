FROM joseluisq/static-web-server:2-debian

# Install Python 10
RUN apt update
RUN apt upgrade -y
RUN apt install -y build-essential zlib1g-dev libncurses5-dev libgdbm-dev libnss3-dev libssl-dev libreadline-dev libffi-dev libsqlite3-dev wget libbz2-dev
RUN wget https://www.python.org/ftp/python/3.10.15/Python-3.10.15.tgz
RUN tar -xf Python-3.10.15.tgz
WORKDIR Python-3.10.15/
RUN ./configure --prefix=/usr/local --enable-optimizations --enable-shared LDFLAGS="-Wl,-rpath /usr/local/lib"
RUN make -j $(nproc)
RUN make altinstall
WORKDIR ..
RUN rm -f Python-3.10.15.tgz
RUN rm -rf Python-3.10.15

# Install node
RUN apt install -y nodejs

# Install pnpm
RUN wget -qO- https://get.pnpm.io/install.sh | ENV="$HOME/.bashrc" SHELL="$(which bash)" bash -

# Install backend requirements
WORKDIR ..
COPY requirements.txt .
RUN pip3.10 install -r requirements.txt
RUN pip3.10 install "uvicorn[standard]"
RUN pip3.10 install python-multipart
RUN rm -f requirements.txt

# Copy source
COPY crossbar_llm crossbar_llm
WORKDIR crossbar_llm

# Install & build frontend
WORKDIR frontend
RUN /root/.local/share/pnpm/pnpm install
RUN /root/.local/share/pnpm/pnpm build
RUN rm -r /public
RUN cp -rf build /public
WORKDIR ..
RUN rm -rf frontend

WORKDIR ..
COPY startup.sh .
RUN chmod +x startup.sh

EXPOSE 8000
EXPOSE 8501

ENTRYPOINT ["./startup.sh"]
