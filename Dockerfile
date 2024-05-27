FROM node:alpine as client-builder

RUN mkdir /app/
WORKDIR /app/

COPY frontend/package.json frontend/package-lock.json .
RUN npm install
COPY frontend .
RUN npm run build


FROM python:3-alpine

ENV PYTHONUNBUFFERED True
RUN mkdir /app/
WORKDIR /app/

COPY requirements.lock pyproject.toml README.md .

# TODO: try removing these extra dependencies/build-dependencies
RUN apk add --no-cache \
    libxslt \
 && apk add --no-cache --virtual build-dependencies \
    gcc \
    libxml2-dev \
    libxslt-dev \
    musl-dev \
 && pip3 install -r requirements.lock \
 && apk del build-dependencies

COPY --from=client-builder /app/dist /app/frontend/dist
COPY . .

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "backend.src.__main__:app"]
