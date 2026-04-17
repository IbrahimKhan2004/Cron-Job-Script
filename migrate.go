package main

import (
	"log"
	"go.mongodb.org/mongo-driver/bson/primitive"
)

func migrate() {
	urls := []string{
		"https://unpleasant-tapir-alexpinaorg-ee539153.koyeb.app/",
		"https://bot-pl0g.onrender.com/",
		"https://brilliant-celestyn-mustafaorgka-608d1ba4.koyeb.app/",
		"https://fsb-latest-yymc.onrender.com/",
		"https://gemini-5re4.onrender.com/",
		"https://late-alameda-streamppl-f38f75e1.koyeb.app/",
		"https://main-diup.onrender.com/",
		"https://marxist-theodosia-ironblood-b363735f.koyeb.app/",
		"https://mltb-x2pj.onrender.com/",
		"https://neutral-ralina-alwuds-cc44c37a.koyeb.app/",
		"https://ssr-fuz6.onrender.com",
		"https://unaware-joanne-eliteflixmedia-976ac949.koyeb.app/",
		"https://worthwhile-gaynor-nternetke-5a83f931.koyeb.app/",
		"https://cronjob-sxmj.onrender.com",
		"https://native-darryl-jahahagwksj-902a75ed.koyeb.app/",
		"https://prerss.onrender.com/skymovieshd/latest-updated-movies",
		"https://gofile-spht.onrender.com",
		"https://gofile-g1dl.onrender.com",
		"https://regex-k9as.onrender.com",
		"https://namechanged.onrender.com",
		"https://telegram-stremio-v9ur.onrender.com",
	}

	initDB()

	for _, url := range urls {
		job := CronJob{
			Name:     "Legacy Job " + primitive.NewObjectID().Hex()[:4],
			URL:      url,
			Interval: 60,
			Status:   "active",
		}
		id, err := addJobDB(job)
		if err != nil {
			log.Printf("Failed to migrate %s: %v", url, err)
		} else {
			log.Printf("Migrated %s with ID %s", url, id.Hex())
		}
	}
}
