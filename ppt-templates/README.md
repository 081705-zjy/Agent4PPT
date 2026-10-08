# PPT Template Profiles

This directory stores deck template profiles used by the local editable renderer.
Profiles are JSON files so generation can apply stable design constraints without
requiring a copied `.pptx` master file.

For a user-provided template, initialize a project first:

```bash
bash scripts/init-project.sh "topic"
# put your JSON profile or .pptx reference into projects/<topic-slug>/templates/
bash scripts/start-app.sh
```

Project-local templates are resolved before built-in templates. This mirrors the
PPT Master project workflow: the template bundle lives inside the project and the
executor must follow it for style planning and rendering.

Each profile provides:

- `template_id`, `name`, `description`
- `palette`: `primary`, `secondary`, `accent`, `neutral`, `text`
- `typography`: `heading`, `body`, `heading_size`, `body_size`
- `layouts`: named layout guidance used by `visual-plan.json`
- `render`: renderer hints such as accent bar height and picture placement

Future `.pptx` master import can be added beside these profiles, but the JSON
profile path is the stable default because it keeps titles, bodies, shapes, and
charts editable.
