package main

import (
"context"
"database/sql"
"net/http"
"os"
"time"

"github.com/gin-gonic/gin"
_ "github.com/go-sql-driver/mysql"
_ "github.com/lib/pq"
"go.mongodb.org/mongo-driver/mongo"
"go.mongodb.org/mongo-driver/mongo/options"
)

func health(c *gin.Context){
engine:=os.Getenv("DB_ENGINE")
host:=os.Getenv("DB_HOST")
port:=os.Getenv("DB_PORT")
name:=os.Getenv("DB_NAME")
user:=os.Getenv("DB_USER")
pass:=os.Getenv("DB_PASSWORD")

switch engine {
case "postgres":
 db,err:=sql.Open("postgres","host="+host+" port="+port+" user="+user+" password="+pass+" dbname="+name+" sslmode=disable")
 if err!=nil||db.Ping()!=nil { c.JSON(500,gin.H{"status":"unhealthy"}); return}
 c.JSON(200,gin.H{"status":"healthy","database":"connected"})
case "mysql":
 db,err:=sql.Open("mysql",user+":"+pass+"@tcp("+host+":"+port+")/"+name)
 if err!=nil||db.Ping()!=nil { c.JSON(500,gin.H{"status":"unhealthy"}); return}
 c.JSON(200,gin.H{"status":"healthy","database":"connected"})
case "mongodb":
 ctx,cancel:=context.WithTimeout(context.Background(),5*time.Second); defer cancel()
 client,err:=mongo.Connect(ctx,options.Client().ApplyURI("mongodb://"+user+":"+pass+"@"+host+":"+port))
 if err!=nil||client.Ping(ctx,nil)!=nil { c.JSON(500,gin.H{"status":"unhealthy"}); return}
 c.JSON(200,gin.H{"status":"healthy","database":"connected"})
default:
 c.JSON(500,gin.H{"error":"unsupported DB_ENGINE"})
}
}
func main(){
r:=gin.Default()
r.LoadHTMLGlob("templates/*")
r.Static("/static","./static")
r.GET("/",func(c *gin.Context){c.HTML(http.StatusOK,"index.html",nil)})
r.GET("/health",health)
r.GET("/api/info",func(c *gin.Context){c.JSON(200,gin.H{"backend":"Gin","cloud":"AWS EC2","version":"1.0"})})
r.Run(":8080") //change 5000 to 8080
}  
