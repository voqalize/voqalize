// Command travel-local runs the Go TravelBrain against the LOCAL Cortex relay
// (pm2 dev stack), the Go analogue of examples/travel/run_local.py.
//
//	cd backend/agent-sdk-go && go run ./cmd/travel-local
//
// It dials ws://localhost:8480/agent as a *platform agent* for the pool the
// locally-seeded demo-travel agent routes to once flipped to deployment.mode =
// cortex (t:demo-tenant:voqal-travel). Auth is a short-lived RS256 JWT signed
// with .dev-keys/platform.pem, which Cortex trusts via CORTEX_PLATFORM_PUBKEYS.
//
// Pair with the /travel console demo at http://localhost:5740/travel after
// flipping demo-travel to cortex (scripts/flip_travel_cortex.py).
package main

import (
	"context"
	"crypto/rsa"
	"fmt"
	"log"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/joho/godotenv"

	"github.com/voqalize/voqalize/sdk/go/brain"
	"github.com/voqalize/voqalize/sdk/go/cortex"
	"github.com/voqalize/voqalize/sdk/go/examples/travel"
)

const poolKey = "t:demo-tenant:voqal-travel" // compute_pool_key("demo-tenant", "voqal-travel")

func main() {
	root := repoRoot()
	_ = godotenv.Load(filepath.Join(root, ".env"))

	cortexURL := os.Getenv("CORTEX_AGENT_URL")
	if cortexURL == "" {
		cortexURL = "ws://localhost:8480/agent"
	}

	priv := loadPrivateKey(filepath.Join(root, ".dev-keys", "platform.pem"))
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	newBrain := func() brain.Brain {
		b, err := travel.New(ctx, "")
		if err != nil {
			log.Fatalf("travel-local: %v", err)
		}
		return b
	}

	lg := logger{}
	agent, err := cortex.New(cortex.Options{
		Version:               "travel-cortex-go/0.1",
		CortexURL:             cortexURL,
		AuthorizationProvider: func() string { return "Bearer " + mintToken(priv) },
		Logger:                lg,
	}, brain.Factory(newBrain, lg))
	if err != nil {
		log.Fatalf("travel-local: %v", err)
	}

	lg.Infof("travel-cortex-go: connecting to %s as pool %s", cortexURL, poolKey)
	if err := agent.Run(ctx); err != nil && ctx.Err() == nil {
		log.Fatalf("travel-local: agent stopped: %v", err)
	}
}

// mintToken signs a fresh platform-agent JWT (iss=platform, aud=cortex).
func mintToken(priv *rsa.PrivateKey) string {
	now := time.Now()
	tok := jwt.NewWithClaims(jwt.SigningMethodRS256, jwt.MapClaims{
		"iss":      "platform",
		"aud":      "cortex",
		"kind":     "platform_agent",
		"agent_id": poolKey,
		"iat":      now.Unix(),
		"exp":      now.Add(time.Hour).Unix(),
	})
	signed, err := tok.SignedString(priv)
	if err != nil {
		log.Fatalf("travel-local: sign token: %v", err)
	}
	return signed
}

func loadPrivateKey(path string) *rsa.PrivateKey {
	pem, err := os.ReadFile(path)
	if err != nil {
		log.Fatalf("travel-local: read %s: %v", path, err)
	}
	key, err := jwt.ParseRSAPrivateKeyFromPEM(pem)
	if err != nil {
		log.Fatalf("travel-local: parse private key: %v", err)
	}
	return key
}

// repoRoot walks up from the cwd to the dir containing .dev-keys.
func repoRoot() string {
	dir, err := os.Getwd()
	if err != nil {
		log.Fatalf("travel-local: getwd: %v", err)
	}
	for {
		if _, err := os.Stat(filepath.Join(dir, ".dev-keys")); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			log.Fatal("travel-local: could not locate repo root (.dev-keys) from cwd")
		}
		dir = parent
	}
}

type logger struct{}

func (logger) Infof(f string, a ...any) { fmt.Printf("INFO  "+f+"\n", a...) }
func (logger) Warnf(f string, a ...any) { fmt.Printf("WARN  "+f+"\n", a...) }
