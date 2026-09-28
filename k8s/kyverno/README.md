# KOMORA Kyverno Security Policies

These policies are the admission-control layer for KOMORA.

They complement Kubernetes Pod Security Admission rather than replacing it. PSA establishes the namespace baseline; Kyverno expresses KOMORA-specific requirements such as the dedicated ServiceAccount, resource declarations, read-only root filesystem, and immutable image tags.

The policies are enforced for workloads in the `komora` namespace.

## Policy groups

- Runtime identity: non-root, dedicated ServiceAccount, no token automount.
- Container isolation: no privileged mode, no privilege escalation, RuntimeDefault seccomp, drop all capabilities, read-only root filesystem.
- Resource governance: CPU and memory requests/limits.
- Host isolation: no hostNetwork, hostPID, or hostIPC.
- Supply chain: no mutable `:latest` image tags.

The signed-image verification gate is handled by the CI/CD supply-chain controls so that the image is signed before deployment and verified by the deployment pipeline.
