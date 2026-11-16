"""How a running job is told to stop (shared by the pipeline and the queue, which would otherwise import each other)"""


class JobCancelled(Exception):
    """Raised at a checkpoint when the job must stop. reason: cancelled (the user asked), shutdown (the server is stopping
    and the job will run again), lost (another worker or the reaper took the job over), deleted (the job row is gone)"""

    def __init__(self, reason: str = "cancelled"):
        super().__init__(reason)
        self.reason = reason
