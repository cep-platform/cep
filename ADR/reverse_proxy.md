# Architectural Decision Record (ADR)

## Context & Problem Statement
We need an edge proxy/reverse proxy solution to handle dynamic routing, SSL termination, traffic distribution and auth middleware. This proxy must be managed externally by a custom, minimal Python-based wrapper that updates routing tables on the fly without causing service disruptions or dropping connections.

Our architectural constraints require that the selected tool:
1. Supports **on-the-fly dynamic reloads** via an API or control plane rather than file system polls or hard service restarts.
2. Maintains a **minimal structural footprint** in terms of binary dependencies and deployment size.
3. Adheres to a strict **fully open-source model** with community or foundational funding, avoiding features locked behind corporate enterprise paywalls (a philosophy similar to the Linux ecosystem).

## Considered Alternatives
We evaluated three primary open-source candidates that support dynamic runtime configurations:
* **Caddy (v2)**
* **Envoy Proxy**
* **HAProxy**

### Comparison Matrix

| Criteria | Caddy | Envoy Proxy | HAProxy |
| :--- | :--- | :--- | :--- |
| **Wrapper Interface** | Native HTTP JSON API | gRPC / xDS API Streaming | Unix Socket Runtime API |
| **Python Ecosystem Fit** | Excellent (Native JSON strings) | Poor (Heavy gRPC/Protobuf layer) | Fair (Requires socket parsing) |
| **Governance Model** | 100% Free/Sponsor-funded | CNCF Foundation Neutral | Core GPL + Commercial Support |
| **Footprint / Size** | Minimal (~40MB Statically Compiled) | Moderate | Minimal |

---

### Pros and Cons of Alternatives

#### Caddy
* **Pros:**
  * **Native JSON API:** Exposes an HTTP administration endpoint accepting pure JSON, matching Python’s native dictionary capabilities flawlessly.
  * **Zero-Downtime Reloads:** Changes applied to the `/load` endpoint instantly hot-swap the active configuration in memory without dropping active connections.
  * **Zero External Dependencies:** Distributed as a single compiled binary requiring no system libraries.
  * **Strict Open-Source Ethics:** Expressly rejects paywalling advanced proxy capabilities, relying entirely on corporate sponsorships and public donations.
* **Cons:**
  * Lacks the multi-vendor foundation governance of a CNCF project.

#### Envoy Proxy
* **Pros:**
  * **CNCF Foundation Governance:** Positioned closest to Linux in terms of vendor neutrality and foundation backing.
  * Extremely robust performance scaling in large microservice meshes.
* **Cons:**
  * **Massive Complexity Layer:** The xDS configuration API relies heavily on complex gRPC streaming protocols. Writing a custom Python control plane requires managing complex protobuf generation, drastically increasing wrapper size and dependency weight.

#### HAProxy
* **Pros:**
  * Exceptionally high concurrency and raw throughput capabilities.
  * Deeply embedded in the standard Linux infrastructure ecosystem.
* **Cons:**
  * **Awkward Wrapper APIs:** Runtime configuration happens over raw Unix sockets or via secondary external packages (Dataplane API), complicating a "minimal wrapper" architecture.

---

## Decision Outcome
**Chosen Option: Caddy**

### Motivation
Caddy fits both developer experience requirements and ideological open-source constraints. 

1. **Minimalism & `uv` Integration:** Because Caddy interacts via a straightforward HTTP JSON payload, our Python wrapper can remain small. It can be implemented as a simple wrapper serialising pydantic config objects to JSON and sending it to a configuration endpoint provided by Caddy
2. **Dynamic Operations:** The native `/load` endpoint allows the Python wrapper to treat the proxy configuration as data structures rather than parsing structural configuration files. Updates don't require downtime
3. **Open Source Alignment:** Caddy's transparent funding structure and strict anti-feature-gate philosophy ensure we will not be hit by hidden license walls as architecture scales.

## Consequences
* **Security Context:** Caddy's admin API endpoint must remain strictly isolated within a secure private network namespace to prevent unauthorized routing overrides.
* **State Management:** As this the reverse proxy config is an additional bit of state to maintain, we'll need to consider our current method of handling state such that we can scale features while remaining stable
