package main

import (
	"context"
	"database/sql"
	"fmt"
	"net/http"
	"os"
	"time"

	"github.com/gin-gonic/gin"
	_ "github.com/go-sql-driver/mysql"
	_ "github.com/lib/pq"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

// dbConfig pulls the connection details injected by Ansible as
// environment variables (see ansible/roles/backend/tasks/main.yaml
// and ansible/vars/{{db_engine}}.yaml).
type dbConfig struct {
	engine string
	host   string
	port   string
	name   string
	user   string
	pass   string
}

func loadDBConfig() dbConfig {
	return dbConfig{
		engine: os.Getenv("DB_ENGINE"),
		host:   os.Getenv("DB_HOST"),
		port:   os.Getenv("DB_PORT"),
		name:   os.Getenv("DB_NAME"),
		user:   os.Getenv("DB_USER"),
		pass:   os.Getenv("DB_PASSWORD"),
	}
}

func checkPostgres(cfg dbConfig) error {
	dsn := fmt.Sprintf(
		"host=%s port=%s user=%s password=%s dbname=%s sslmode=disable",
		cfg.host, cfg.port, cfg.user, cfg.pass, cfg.name,
	)
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return err
	}
	defer db.Close()
	db.SetConnMaxLifetime(5 * time.Second)
	return db.Ping()
}

func checkMySQL(cfg dbConfig) error {
	dsn := fmt.Sprintf("%s:%s@tcp(%s:%s)/%s", cfg.user, cfg.pass, cfg.host, cfg.port, cfg.name)
	db, err := sql.Open("mysql", dsn)
	if err != nil {
		return err
	}
	defer db.Close()
	db.SetConnMaxLifetime(5 * time.Second)
	return db.Ping()
}

func checkMongo(cfg dbConfig) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	uri := fmt.Sprintf(
		"mongodb://%s:%s@%s:%s/%s?authSource=admin",
		cfg.user, cfg.pass, cfg.host, cfg.port, cfg.name,
	)
	client, err := mongo.Connect(ctx, options.Client().ApplyURI(uri))
	if err != nil {
		return err
	}
	defer client.Disconnect(ctx)
	return client.Ping(ctx, nil)
}

func health(c *gin.Context) {
	cfg := loadDBConfig()

	// db_engine is passed as "postgres", "mysql", or "mongo" — matching
	// the values used throughout the Terraform/Ansible project, not
	// "postgresql"/"mongodb".
	var err error
	switch cfg.engine {
	case "postgres":
		err = checkPostgres(cfg)
	case "mysql":
		err = checkMySQL(cfg)
	case "mongo":
		err = checkMongo(cfg)
	default:
		c.JSON(http.StatusInternalServerError, gin.H{
			"status": "unhealthy",
			"error":  fmt.Sprintf("unsupported DB_ENGINE: %q", cfg.engine),
		})
		return
	}

	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"status":   "unhealthy",
			"database": "not connected",
			"engine":   cfg.engine,
			"error":    err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"status":   "healthy",
		"database": "connected",
		"engine":   cfg.engine,
	})
}

func info(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"backend": "Gin",
		"cloud":   "AWS EC2",
		"version": "1.0",
	})
}

func main() {
	r := gin.Default()
	r.LoadHTMLGlob("templates/*")
	r.Static("/static", "./static")

	r.GET("/", func(c *gin.Context) {
		c.HTML(http.StatusOK, "index.html", nil)
	})
	r.GET("/health", health)
	r.GET("/api/info", info)

	// Must match the container port Ansible publishes for gin: "8080:8080"
	r.Run(":8080")
}
