# How to update requirements.txt

Install pipreqs and pip-tools:

```sh
python -m pip install pipreqs pip-tools
```

Update requirements.txt

```sh
python -m pipreqs.pipreqs --encoding utf-8 --force --savepath=requirements.in --ignore .venv,.venv_old,.vscode,build,.mypy_cache,"./" && pip-compile --resolver=backtracking
```
