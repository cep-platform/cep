# Architectural Decision Record (ADR)

## Context & Problem Statement

Cep needs a persistent storage abstraction (REQUIREMENTS.md §1.3): pools,
volumes, backups, and eventually replication across federation peers.

An initial implementation was built against the Docker backend: pools and
volumes were plain directories under `CEP_STORAGE_PATH`, managed by the
appstore (filesystem operations), with cep-main tracking metadata in
`storage_db.json`. That implementation is removed by this decision.

Problems that motivated the removal:

1. **Nothing consumed it.** App templates use Compose named volumes. The one
   attempt to wire storage into deploys (PR #30, auto-creating
   `default_<volume>` pools/volumes) was reverted; the CRUD survived as an
   island.
2. **Dual source of truth.** cep-main's metadata and the appstore's
   filesystem view could disagree (manual changes, or a crash between the
   proxy call and the metadata save). Drift wedged pools into an undeletable
   `404 "Pool is not empty"` state that required host filesystem access to
   resolve.
3. **No attach capability.** The defining feature of a volume — being
   attached to a running app — was never implemented.
4. **Untested and partly broken.** No test coverage; `cep storage pool list`
   printed placeholder stats for every pool; error codes were misclassified.
5. **Privileged dead surface.** The endpoints lived on the unauthenticated,
   docker-sock-mounted appstore and created/deleted arbitrary directories on
   a host bind mount.

## Decision Outcome

**Remove the Docker-based storage layer now; design and build it against the
Incus backend when the container runtime switch happens.** REQUIREMENTS.md
§1.3 stays as the goal — this defers the implementation, not the requirement.

Incus mapping for the future implementation:

- cep **pool** ≈ Incus *storage pool*: the backend definition (driver `dir`,
  `zfs`, `btrfs`, `lvm`, `ceph`). Features such as quotas, snapshots and
  migration come from the driver. A single-node MVP should default to one
  hidden pool — pools are backend plumbing, not a user-facing concept, and
  should not be exposed until a driver choice actually matters.
- cep **volume** ≈ Incus *custom volume*: the unit that gets attached to an
  app instance as a disk device. **Attaching is the capability the removed
  implementation never had, and the entire point of volumes.**
- **Incus is the source of truth** for pools and volumes; it tracks them
  natively. Cep keeps only ownership metadata on the app record
  (`AppRecord.volumes`), not a parallel store. Storage state is deliberately
  *not* merged into `NetworkStore`.

Future flow: the AppSpec declares storage needs (`name`, `size`, …) → create
the Incus volume → attach it as a device → record ownership on `AppRecord`.

## Consequences

- Removed: the `cep storage` CLI, the `/storage` routers on cep-main and the
  appstore, `PoolRecord`/`VolumeRecord`/`StorageStore`, `storage_db.json`,
  and the `CEP_STORAGE_PATH` bind mount.
- REQUIREMENTS.md §1.3 is unchanged; storage work resumes with the Incus
  backend, with this ADR's mapping as the starting point.
- The old implementation remains in git history if reference is needed.