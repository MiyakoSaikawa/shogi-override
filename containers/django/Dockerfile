FROM python:3.8

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /code

RUN pip install --upgrade pip && pip install pipenv

COPY ./Pipfile /tmp/Pipfile
COPY ./Pipfile.lock /tmp/Pipfile.lock

WORKDIR /tmp
RUN pipenv install --system --deploy --ignore-pipfile

RUN pip install gunicorn psycopg2-binary

WORKDIR /code
COPY ./shogi_override /code

COPY ./containers/django/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

CMD ["/usr/local/bin/entrypoint.sh"]
