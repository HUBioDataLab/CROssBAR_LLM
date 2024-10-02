FROM python:3.10-bookworm

COPY . streamlit
WORKDIR streamlit
RUN pip install -r requirements.txt

ENTRYPOINT [ "streamlit" ]
CMD [ "run", "crossbar_llm/streamlit_interface.py", "--server.address=0.0.0.0", "--server.baseUrlPath=/llm"]
