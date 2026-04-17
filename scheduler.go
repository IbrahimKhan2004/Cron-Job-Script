package main

import (
	"fmt"
	"log"
	"net/http"
	"time"

	"github.com/robfig/cron/v3"
)

var (
	c        *cron.Cron
	jobMap   map[string]cron.EntryID
)

func init() {
	c = cron.New(cron.WithSeconds())
	jobMap = make(map[string]cron.EntryID)
}

func startScheduler() {
	refreshScheduler()
	c.Start()
}

func refreshScheduler() {
	jobs, err := getAllJobs()
	if err != nil {
		log.Printf("Error fetching jobs for scheduler: %v", err)
		return
	}

	activeJobsInDB := make(map[string]bool)

	for _, job := range jobs {
		jobID := job.ID.Hex()
		if job.Status == "active" {
			activeJobsInDB[jobID] = true

			// If job already in scheduler, replace it to handle interval changes
			if entryID, exists := jobMap[jobID]; exists {
				c.Remove(entryID)
			}

			spec := fmt.Sprintf("@every %ds", job.Interval)
			url := job.URL
			entryID, err := c.AddFunc(spec, func() {
				pingURL(url)
			})
			if err != nil {
				log.Printf("Error adding job %s to scheduler: %v", job.Name, err)
				continue
			}
			jobMap[jobID] = entryID
		} else {
			// Job is not active in DB, ensure it's removed from scheduler
			if entryID, exists := jobMap[jobID]; exists {
				c.Remove(entryID)
				delete(jobMap, jobID)
			}
		}
	}

	// Remove jobs that were deleted from DB
	for jobID, entryID := range jobMap {
		if !activeJobsInDB[jobID] {
			c.Remove(entryID)
			delete(jobMap, jobID)
		}
	}
}

func pingURL(url string) {
	client := http.Client{
		Timeout: 10 * time.Second,
	}
	resp, err := client.Get(url)
	if err != nil {
		log.Printf("[PING] %s - Error: %v", url, err)
		return
	}
	defer resp.Body.Close()
	log.Printf("[PING] %s - Status: %d", url, resp.StatusCode)
}
