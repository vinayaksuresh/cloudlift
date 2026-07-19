import subprocess


class ArtifactRegistryClient(object):
    def __init__(self, config):
        self.config = config

    def image_uri(self, service_name, version):
        location = self.config.location
        location_parts = location.rsplit("-", 1)
        if len(location_parts) == 2 and location_parts[1].isalpha() and len(location_parts[1]) == 1:
            raise ValueError(
                "Artifact Registry location must be regional or multi-regional, not zonal: {}".format(
                    location
                )
            )
        return "{}-docker.pkg.dev/{}/{}/{}:{}".format(
            location,
            self.config.project_id,
            self.config.artifact_registry_repository,
            service_name,
            version,
        )

    def tag_and_push(self, service_name, local_tag, additional_tags=None):
        local_tag = local_tag or "latest"
        additional_tags = additional_tags or []
        source_image = "{}:{}".format(service_name, local_tag)
        pushed = []
        for tag in [local_tag] + list(additional_tags):
            target_image = self.image_uri(service_name, tag)
            subprocess.check_call(["docker", "tag", source_image, target_image])
            subprocess.check_call(["docker", "push", target_image])
            pushed.append(target_image)
        return pushed
