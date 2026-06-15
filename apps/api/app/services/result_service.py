from app.services.compat import legacy


def get_logs(task_id):
    return legacy().get_logs(task_id)


def get_outputs(task_id):
    return legacy().get_outputs(task_id)


def get_result_summary(task_id):
    return legacy().get_result_summary(task_id)


def get_task_artifact_manifest(task_id):
    return legacy().get_task_artifact_manifest(task_id)


def get_task_artifact(task_id, relative_path):
    return legacy().get_task_artifact(task_id, relative_path)


def bold_group_analysis(project_id, req):
    return legacy().bold_group_analysis(project_id, req)


def bold_descriptive_review(project_id, req):
    return legacy().bold_descriptive_review(project_id, req)
