# Copyright (C) 2020-present, Irene Adler 💜 (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Scheduler: persistent jobs (reminders, birthdays, periodic messages) that survive restarts.

.. code-block:: python

    class Reminders(Cog):
        @scheduler.handler("reminder", max_lateness=dt.timedelta(days=7))
        async def send_reminder(self, job: scheduler.Job[ReminderData]) -> None:
            await channel.send(job.data["text"])  # return normally: done (or repeated); raise: retried


    await bot.scheduler.schedule("reminder", WallTime(local, "Europe/Berlin"), data={"text": "..."}, user_id=...)
"""

from .jobs import *
from .recurrence import *
from .scheduler import *
from .walltime import *
