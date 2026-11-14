# Runbook: submitting our policy

Condensed from Aalto's `aaltonomous/docs/participants/SUBMISSION.md`. If they disagree, Aalto's file wins.

**Already pushed (Sat 14 Nov evening, public package `ghcr.io/samer-cyber/bot-icelli-policy`, Samer's account):**
- v1.4, the candidate: `ghcr.io/samer-cyber/bot-icelli-policy@sha256:cd8311e9f64ea25703d9c70a645b44091dc5a00d8b5f75dc54f29720f6fd7f8d`
- v1.3, the fallback: `ghcr.io/samer-cyber/bot-icelli-policy@sha256:60ef1b8980de11f9448da5de27234bf3d9f3b3be682f1914a2c0532c2ed504c4`
- New versions: on `samer-v1-sim` (logged in to GHCR) `docker tag bot-icelli/policy:vN ghcr.io/samer-cyber/bot-icelli-policy:vN && docker push ghcr.io/samer-cyber/bot-icelli-policy:vN`; the push prints the digest for the form.

1. **Pass the local checks:**
   - `make check`
   - on the sim machine: `make eval TASK=sort_fixed TRIALS=20` and `TASK=sort_language`, both with gate PASS (exit 0)
2. **Build the image:** `make docker-build IMAGE=$REGISTRY_IMAGE:vN POLICY=<name>`. Weights go in `policy/weights/` before building. Faster on the x86 Verda machine.
3. **Test the image:** `make docker-check IMAGE=$REGISTRY_IMAGE:vN`. This checks startup < 120 s and ≥ 27 Hz.
4. **Push it:** `docker push $REGISTRY_IMAGE:vN`. Note the `sha256:…` digest it prints.
5. **Fill in the web form** (link on the Aalto Discord channel):
   ```yaml
   team: <team id from kickoff>
   image: ghcr.io/<owner>/bot-icelli-policy@sha256:...   # pin the digest, not just a tag
   tasks: [sort_fixed, sort_language]
   contact: "<name> on Discord"
   ```
6. **Log it:** add an `eval/RESULTS.md` row (image digest) and a line in `docs/PROGRESS.md`.

**Rules:**
- The organisers' pre-check tests the pull, linux/amd64, ≤ 40 GB, startup < 120 s and ≥ 27 Hz. A failure comes back with the reason.
- **The last image submitted before the Sunday deadline is the one that runs in the finals.** Don't submit something untested late.
