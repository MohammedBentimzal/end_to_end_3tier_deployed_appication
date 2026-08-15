# --- build stage ---
FROM golang:1.22-bookworm AS builder

WORKDIR /app

COPY go.mod ./
COPY main.go ./
COPY templates ./templates
COPY static ./static

# go.sum wasn't provided, so resolve and lock dependencies at build time.
RUN go mod tidy && go build -o ginbackend main.go

# --- final stage ---
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/ginbackend ./ginbackend
COPY --from=builder /app/templates ./templates
COPY --from=builder /app/static ./static

EXPOSE 8080

CMD ["./ginbackend"]
