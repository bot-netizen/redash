# The local cluster, and what keeps breaking

The test install is **minikube**, reached at **http://localhost:5090** through
`kubectl port-forward svc/sqldesk 5090:5000`. That forward dies on every
rollout and every node restart; restart it. **5090 is the user's** — use 5091
for anything of your own, and never kill a forward you did not start.

## Building an image for it

**Never `minikube image build`.** It builds *inside* the node container, which
shares its memory limit with the API server — on 2026-10-03 it took the API
server to `Stopped`, killed the port-forward, and left the server pod unable to
restart because `failed to sync secret cache` needs the API server that is
down. Build on the host and load it:

```
docker build -t sqldesk:0.7-devNN .
minikube image load sqldesk:0.7-devNN
helm upgrade sqldesk charts/sqldesk --reset-then-reuse-values \
  --timeout 15m --set image.tag=0.7-devNN \
  --set streams.enabled=true --set uploads.enabled=true
```

`--reset-then-reuse-values`, not `--reuse-values`: the latter keeps the *old
chart's* defaults, so new values arrive nil.

`streams.enabled` and `uploads.enabled` must be set explicitly — both default
to **off** since 2026-10-03, and the local install needs them for testing.

**Disk.** minikube runs on the docker driver, so the node shares the host's
58 GB. Check `docker run --rm alpine df -h /` before a build and prune old
`sqldesk:0.7-dev*` tags; each is about 1.5 GB.

**A faster loop for frontend-only changes:** `pnpm run build` on the host,
then `docker build --build-arg skip_frontend_build=true` for a base image and
a two-line Dockerfile that copies `client/dist` onto it. `client/dist` is in
`.dockerignore`, so the copy needs its own scratch build context.

## The Kafka demo stack

`redpanda`, `orders-producer` and `payments-producer` deployments, with topics
`orders` and `payments`.

**redpanda lost every topic on each node restart** until it was given a 2 Gi
PVC at `/var/lib/redpanda/data` on 2026-10-03. If topics ever vanish again,
the symptom is the nasty one — consumers run with **no error and no rows**,
which looks exactly like a bug in SQLDesk. Recover with:

```
kubectl exec deploy/redpanda -- rpk topic create orders payments -p 1
kubectl rollout restart deploy/orders-producer deploy/payments-producer
```

**Streams are cold unless somebody is watching.** That is the design, not a
fault: a stream nobody has looked at for ten minutes stops consuming. To drive
the path without the UI, check in as a watcher, run the supervisor, then query:

```python
from sqldesk.app import create_app
app = create_app(); app.app_context().push()
from sqldesk import models
from sqldesk.streams import watching
from sqldesk.tasks.streams import supervise_streams
for s in models.Stream.query.all():
    watching.check_in(s.id, "smoke")
supervise_streams()
```

Copy the script to **`/app`** inside the pod, not `/tmp` — Python puts the
script's own directory on `sys.path`, so from `/tmp` the import of `sqldesk`
fails.

## Memory

The node has **5.8 GiB** since 2026-10-03 (it was 3.1, where everything died
whenever a second thing ran). Docker Desktop has 6 GB. **One heavy job at a
time** — a webpack build alongside a test container and minikube wedged the
daemon at 4 GB and took minikube's container with it.

## Checking a page without signing in

**Never enter credentials to look at something.** Two ways that work:

- A public dashboard link: `models.ApiKey.create_for_object`, then
  `/public/dashboards/<token>`.
- For anything needing a session (admin pages, edit mode), write a static HTML
  file with the same class names, link the built stylesheets from
  `/static/<hash>.css`, drop it in `client/dist/`, and open
  `/static/<name>.html`. The pod's filesystem is ephemeral, so it cleans
  itself up on the next rollout.

Downscaled screenshots are not evidence about small text. Measure with
`getComputedStyle` and `getBoundingClientRect` rather than reading a picture.
