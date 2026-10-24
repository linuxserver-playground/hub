"""
A Kubernetes manifest per image from `runtime` and `publish.kubernetes`: a ConfigMap with the environment,
a PersistentVolumeClaim per persisted path, a Deployment or StatefulSet, and a Service. Security settings
that need a cluster decision (privileged, capabilities, devices, seccomp) are emitted and explained as comments.

Import: `kubectl apply -f https://<hub>/stores/kubernetes/<name>.yaml` (edit storage sizes and secrets first).
"""

from __future__ import annotations

from typing import Any

from .common import Files, GenerateContext, ImageInput, yaml_text

Json = dict[str, Any]


def _labels(name: str) -> Json:
    return {"app.kubernetes.io/name": name, "app.kubernetes.io/managed-by": "linuxserver-hub"}


def _claim_name(name: str, path: str) -> str:
    segment = path.strip("/").replace("/", "-") or "root"
    return f"{name}-{segment}"


def persistence(image: ImageInput) -> list[str]:
    configured = image.manifest.get("publish", {}).get("kubernetes", {}).get("persistence")
    if configured:
        return list(configured)
    return [v["path"] for v in image.rt["volumes"] if not v["optional"]]


def _security_notes(image: ImageInput) -> list[str]:
    rt = image.rt
    notes: list[str] = []
    if rt["privileged"]:
        notes.append("privileged: the image asks for --privileged; securityContext.privileged is set below.")
    for cap in rt["cap_add"]:
        suffix = " (optional)" if cap["optional"] else ""
        notes.append(f"capability {cap['cap']}{suffix}: {cap['description'] or 'required by the application'}.")
    for sec in rt["security_opt"]:
        notes.append(
            f"security_opt {sec['run']}: {sec['description']} (map to a seccompProfile or AppArmor annotation)."
        )
    for device in rt["devices"]:
        notes.append(
            f"device {device['path']}: {device['description']} (needs a device plugin or hostPath; not emitted)."
        )
    if rt["network"] and rt["network"]["mode"] == "host":
        notes.append("network: host networking is required; hostNetwork is set and no Service is emitted.")
    if rt["readonly"]["supported"]:
        notes.append("readOnlyRootFilesystem is supported by this image; enable it once /config and /tmp are mounted.")
    if rt["nonroot"]["supported"]:
        notes.append("runAsNonRoot is supported by this image (set runAsUser and drop PUID/PGID).")
    return notes


def render(image: ImageInput) -> str:
    name, rt = image.name, image.rt
    publish = image.manifest.get("publish", {}).get("kubernetes", {})
    workload = publish.get("workload", "Deployment")
    labels = _labels(name)
    env = {e["name"]: e["value"] for e in image.env_items(optional=False)}
    host_network = bool(rt["network"] and rt["network"]["mode"] == "host")
    claims = persistence(image)
    docs: list[Json] = []
    if env:
        docs.append(
            {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {"name": f"{name}-env", "labels": labels},
                "data": env,
            }
        )
    for path in claims:
        docs.append(
            {
                "apiVersion": "v1",
                "kind": "PersistentVolumeClaim",
                "metadata": {"name": _claim_name(name, path), "labels": labels},
                "spec": {"accessModes": ["ReadWriteOnce"], "resources": {"requests": {"storage": "1Gi"}}},
            }
        )
    ports = []
    for port in rt["ports"]:
        if port["optional"]:
            continue
        number, _, proto = port["internal"].partition("/")
        ports.append(
            {
                "name": (port["name"] or f"port-{number}").lower()[:15],
                "containerPort": int(number),
                "protocol": (proto or "tcp").upper(),
            }
        )
    container: Json = {"name": name, "image": image.image_ref, "imagePullPolicy": "IfNotPresent"}
    if env:
        container["envFrom"] = [{"configMapRef": {"name": f"{name}-env"}}]
    if ports and not host_network:
        container["ports"] = ports
    mounts = [{"name": _claim_name(name, path), "mountPath": path} for path in claims]
    optional_mounts = [v for v in rt["volumes"] if v["path"] not in claims and not v["optional"]]
    mounts += [{"name": _claim_name(name, v["path"]), "mountPath": v["path"]} for v in optional_mounts]
    if mounts:
        container["volumeMounts"] = mounts
    security: Json = {}
    if rt["privileged"] is True:
        security["privileged"] = True
    caps = [c["cap"] for c in rt["cap_add"] if not c["optional"]]
    if caps:
        security["capabilities"] = {"add": caps}
    if security:
        container["securityContext"] = security
    pod: Json = {"containers": [container]}
    if host_network:
        pod["hostNetwork"] = True
    volumes = [
        {"name": _claim_name(name, p), "persistentVolumeClaim": {"claimName": _claim_name(name, p)}} for p in claims
    ]
    volumes += [{"name": _claim_name(name, v["path"]), "emptyDir": {}} for v in optional_mounts]
    if volumes:
        pod["volumes"] = volumes
    spec: Json = {
        "replicas": 1,
        "selector": {"matchLabels": {"app.kubernetes.io/name": name}},
        "template": {"metadata": {"labels": labels}, "spec": pod},
    }
    if workload == "StatefulSet":
        spec["serviceName"] = name
    else:
        spec["strategy"] = {"type": "Recreate"}
    docs.append({"apiVersion": "apps/v1", "kind": workload, "metadata": {"name": name, "labels": labels}, "spec": spec})
    if ports and not host_network:
        docs.append(
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {"name": name, "labels": labels},
                "spec": {
                    "selector": {"app.kubernetes.io/name": name},
                    "ports": [
                        {
                            "name": p["name"],
                            "port": p["containerPort"],
                            "targetPort": p["containerPort"],
                            "protocol": p["protocol"],
                        }
                        for p in ports
                    ],
                },
            }
        )
    header = [
        f"# {image.title}: generated by the hub from {image.repo_url}/blob/{image.ctx['release_branch']}/image.yml"
    ]
    header += ["# Storage sizes are placeholders; secrets belong in a Secret, not this ConfigMap."]
    notes = _security_notes(image)
    if notes:
        header.append("# Security notes:")
        header += [f"#   - {note}" for note in notes]
    return "\n".join(header) + "\n" + "".join(f"---\n{yaml_text(doc)}" for doc in docs)


def generate(ctx: GenerateContext) -> Files:
    files: Files = {}
    for image in ctx.current:
        if image.manifest.get("publish", {}).get("kubernetes", {}).get("enabled", True):
            files[f"{image.name}.yaml"] = render(image)
    return files
