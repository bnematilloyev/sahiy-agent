# Multi-stage build for Go sahiy-agent (API + Telegram bot).
FROM golang:1.26-alpine AS build

WORKDIR /src
RUN apk add --no-cache git

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /out/sahiy-api ./cmd/api
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /out/sahiy-bot ./cmd/bot

FROM alpine:3.20

RUN apk add --no-cache ca-certificates tzdata
WORKDIR /app

COPY --from=build /out/sahiy-api /usr/local/bin/sahiy-api
COPY --from=build /out/sahiy-bot /usr/local/bin/sahiy-bot

EXPOSE 8001

# Default: HTTP API (override to sahiy-bot for Telegram polling).
CMD ["sahiy-api"]
