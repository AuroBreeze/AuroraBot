python -m venv .venv

call .venv/Scripts/activate

python -m pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

pip install -e .

python main.py