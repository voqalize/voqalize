// Command travel-direct runs the Go TravelBrain as an inbound DIRECT server —
// the Cortex-free path. PyGato dials this process straight at
// ws://localhost:8788/s/{session_id} (one socket per session), with no Cortex
// relay anywhere in the loop.
//
//	cd backend/agent-sdk-go && go run ./cmd/travel-direct
//
// It is the direct-mode analogue of ./cmd/travel-local (which speaks to the
// Cortex relay). Same TravelBrain, same Vql* protocol, same media path — only
// the transport differs: an inbound serve_direct server instead of an outbound
// relay agent.
//
// Auth: this local demo sets AllowUnverified (local dev only). The SDK's embedded
// platform keys (platform_keys.go) are the PRODUCTION pygato signer, but the
// local dev PyGato signs brain tokens with the dev key, which the prod key won't
// verify — so verification is skipped here. A real customer runs the SDK default
// (no options), which verifies against the embedded prod key with no config.
//
// Pair with the /travel console demo at http://localhost:5740/travel after
// flipping demo-travel to deployment.mode=direct with
// brain_url=ws://localhost:8788 (scripts/flip_travel_direct.py in controlplane).
package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"

	"github.com/joho/godotenv"

	"github.com/voqalize/voqalize/sdk/go/brain"
	"github.com/voqalize/voqalize/sdk/go/cortex"
	"github.com/voqalize/voqalize/sdk/go/examples/travel"
)

func main() {
	root := repoRoot()
	_ = godotenv.Load(filepath.Join(root, ".env"))

	addr := os.Getenv("TRAVEL_DIRECT_ADDR")
	if addr == "" {
		addr = "localhost:8788"
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	newBrain := func() brain.Brain {
		b, err := travel.New(ctx, "")
		if err != nil {
			log.Fatalf("travel-direct: %v", err)
		}
		return b
	}

	lg := logger{}
	// No PublicKeysPEM ⇒ connections accepted unverified (local dev). The brain
	// factory runs once per inbound session, exactly like the Cortex path.
	server, err := cortex.NewDirectServer(brain.Factory(newBrain, lg), cortex.DirectOptions{
		Logger:          lg,
		AllowUnverified: true, // local dev: embedded keys are prod; local PyGato signs with the dev key
	})
	if err != nil {
		log.Fatalf("travel-direct: %v", err)
	}

	lg.Infof("travel-direct: serving TravelBrain at ws://%s/s/{session_id} (Cortex-free)", addr)
	if err := server.ListenAndServe(ctx, addr); err != nil && ctx.Err() == nil {
		log.Fatalf("travel-direct: server stopped: %v", err)
	}
}

// repoRoot walks up from the cwd to the dir containing .dev-keys.
func repoRoot() string {
	dir, err := os.Getwd()
	if err != nil {
		log.Fatalf("travel-direct: getwd: %v", err)
	}
	for {
		if _, err := os.Stat(filepath.Join(dir, ".dev-keys")); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			log.Fatal("travel-direct: could not locate repo root (.dev-keys) from cwd")
		}
		dir = parent
	}
}

type logger struct{}

func (logger) Infof(f string, a ...any) { fmt.Printf("INFO  "+f+"\n", a...) }
func (logger) Warnf(f string, a ...any) { fmt.Printf("WARN  "+f+"\n", a...) }
