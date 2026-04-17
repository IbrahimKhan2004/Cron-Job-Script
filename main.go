package main

import (
	"net/http"
	"os"

	"github.com/gin-gonic/gin"
	"go.mongodb.org/mongo-driver/bson"
)

func main() {
	initDB()
	go startScheduler()

	// Run migration if the environment variable is set
	if os.Getenv("RUN_MIGRATION") == "true" {
		migrate()
	}

	router := gin.Default()
	router.LoadHTMLGlob("templates/*")

	// UI Route
	router.GET("/", func(c *gin.Context) {
		c.HTML(http.StatusOK, "index.html", nil)
	})

	// API Routes
	router.GET("/jobs", func(c *gin.Context) {
		jobs, err := getAllJobs()
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, jobs)
	})

	router.POST("/jobs", func(c *gin.Context) {
		var job CronJob
		if err := c.ShouldBindJSON(&job); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}

		id, err := addJobDB(job)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}

		refreshScheduler()
		c.JSON(http.StatusCreated, gin.H{"id": id.Hex()})
	})

	router.PATCH("/jobs/:id", func(c *gin.Context) {
		id := c.Param("id")
		var updateData bson.M
		if err := c.ShouldBindJSON(&updateData); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}

		if err := updateJobDB(id, updateData); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}

		refreshScheduler()
		c.JSON(http.StatusOK, gin.H{"message": "updated"})
	})

	router.DELETE("/jobs/:id", func(c *gin.Context) {
		id := c.Param("id")
		if err := deleteJobDB(id); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}

		refreshScheduler()
		c.JSON(http.StatusOK, gin.H{"message": "deleted"})
	})

	router.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	router.Run(":" + port)
}

func runMigration() {
	migrate()
}
