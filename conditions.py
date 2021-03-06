import datetime
from msrest.authentication import BasicAuthentication
from vsts.vss_connection import VssConnection

# has annotation 'allowCleanup': 'true'
def AnnotationAllowCleanupIsTrueCondition():
    def satisfy(namespace):
        """return true if it has 'allowCleanup': 'true' in annotations"""

        print("%s: Checking annotation condition." % namespace.metadata.name)
        annotations = namespace.metadata.annotations
        result = annotations is not None and ('allowCleanup' in annotations) and annotations['allowCleanup'].lower() == 'true'

        print("%s: Result of annotation condition: %s" % (namespace.metadata.name, result))
        return result
    return satisfy

# no new deployment for certain hours, default to 24
def InactiveDeploymentCondition(api_client_v1beta1, max_inactive_hours):
    max_inactive_time = datetime.timedelta(hours=int(max_inactive_hours))
    api_client = api_client_v1beta1

    def satisfy(namespace):
        """return true if no active deployments"""

        print("%s: Checking inactive condition." % namespace.metadata.name)
        deployments = api_client.list_namespaced_deployment(namespace.metadata.name)

        def is_active(deployment_condition):
            timezone = deployment_condition.last_update_time.tzinfo
            return (datetime.datetime.now(timezone) - deployment_condition.last_update_time) <= max_inactive_time

        def checkdeployment(d):
            return any(is_active(c) for c in d.status.conditions)

        # at least one deployment is updated within max_inactive_days days, we consider this namespace active
        result = not any(checkdeployment(d) for d in  deployments.items)

        print("%s: Result of inactive condition: %s" % (namespace.metadata.name, result))
        return result
    return satisfy

# detect whether git ref is deleted in VSTS
# we don't use branch name because PR will create refs instead of a branch
def VSTSRefDeletedCondition(vsts_pat):
    """Form a VSTS Branch is deleted condition

    :param vsts_pat: VSTS Pat that has Code Reading permission
    """
    credentials = BasicAuthentication('', vsts_pat)
    vsts_base_url_key = "vstsBaseUrl"
    vsts_repository_id_key = "vstsRepositoryId"
    ref_key = "gitRef"

    def satisfy(namespace):
        print("%s: Checking vsts ref deleted condition." % namespace.metadata.name)

        if (
                namespace.metadata.annotations is None
                or vsts_base_url_key not in namespace.metadata.annotations
                or vsts_repository_id_key not in namespace.metadata.annotations
                or ref_key not in namespace.metadata.annotations
        ):
            print("Can't find vsts info in %s" % namespace.metadata.name)
            return False

        # vsts_base_url -- a vsts base url like: https://your-acount.visualstudio.com/DefaultCollection
        vsts_base_url = namespace.metadata.annotations[vsts_base_url_key]
        vsts_repository_id = namespace.metadata.annotations[vsts_repository_id_key]
        ref_name = namespace.metadata.annotations[ref_key]

        connection = VssConnection(base_url=vsts_base_url, creds=credentials)
        client = connection.get_client('vsts.git.v4_0.git_client.GitClient')
        all_refs = [ref.name for ref in client.get_refs(vsts_repository_id)]
        result = ref_name not in all_refs

        print("%s: Result of vsts ref deleted condition: %s" % (namespace.metadata.name, result))
        return result
    return satisfy


def NotWhitelisted(whitelist):
    def satisfy(namespace):
        whitelisted = namespace.metadata.name in whitelist
        if whitelisted:
            print("%s is whitelisted" % namespace.metadata.name)
        return not whitelisted
    return satisfy

#suprised there's not a built in function for this
def AND(*conditions):
    return lambda namespace: all(c(namespace) for c in conditions)

def OR(*conditions):
    return lambda namespace: any(c(namespace) for c in conditions)
        