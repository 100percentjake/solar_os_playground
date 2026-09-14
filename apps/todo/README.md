# Todo List

Todo List is an offline graphical task manager for SolarOS. It keeps quick
one-off work, recurring chores, and project-specific lists together without
requiring a network connection.

## Features

- A Today list containing open general tasks, today's recurring tasks, and
  tasks completed today.
- Projects with independent task lists and full completion history.
- Daily, weekday, multi-day weekly, numbered-day monthly, and Nth-weekday
  monthly recurring-task templates.
- Edit, pause, resume, or remove existing recurrence rules.
- Open-task sorting by creation time or name.
- Optional added and completion dates, with four display formats.
- Optional hiding of completed tasks.
- Independent clearing of completed general or project tasks.
- Plain-text and Markdown exports to `/Downloads`.
- Atomic, versioned JSON storage beside the installed app.
- Recovery from a complete temporary or backup state file after an interrupted
  save.

Recurring templates create no backlog. When the app opens, each active
template creates at most one task for the current day if its schedule is due.
Completed recurring instances remain ordinary task history.

## Controls

- Up/Down or `j`/`k`: move through a list.
- Enter or Space: complete or reopen the selected task.
- `a`: add a one-off task.
- `r`: add a recurring task.
- `e`: rename the selected task.
- `x` or Delete: delete the selected task or project.
- `o`: switch open-task sorting between creation time and name.
- `p`: open Projects from Today.
- `s`: open Settings from Today.
- Escape, Left, or `q`: go back or exit.

The interface is designed for a 400 by 300 pixel reflective LCD but reads the
actual display dimensions at runtime. It redraws only after input or data
changes, never continuously in the background.

Weekly setup uses Space to toggle one or more weekdays and `s` to save the
selection. Monthly setup can use a numbered calendar day or a rule such as
"the second Tuesday" or "the last Friday". Existing rules are managed from
Settings under **Manage recurring tasks**.

Deleting an ordinary task removes it permanently. Deleting a generated
recurring task dismisses only that occurrence, so it does not immediately
reappear and the recurrence continues on its next scheduled day. Recurrence
creation and schedule editing require a valid SolarOS clock.

## Storage and exports

State is saved in `todo.json` beside the application. Writes first go to a
temporary file and are renamed into place, reducing the risk of corruption if
power is interrupted. The previous complete file is retained as a backup until
the replacement is safely in place. On a direct `/apps` installation the usual
path is:

```text
/apps/todo/todo.json
```

Exports are written as `todo-list-YYYY-MM-DD.txt` or `.md` under `/Downloads`.
They include the general list, every project, completion dates, and recurring
template status.

## Requirements

Todo List requires SolarOS 4.8.4 or newer, the Python runtime, storage, and a
graphical display with keyboard input.
