# Architect Memory — PAGB Reconstruction

## Architecture Decision: Qt Mixin Refactoring (2026-04-19)

### Problem
- 8 Qt widgets manually hardcode forms for each Pydantic model field
- Adding new OR type requires editing ORPanel dropdown
- Adding new map property requires editing MapViewer switch chain
- No way for a data model instance to "show itself"
- ParamPanel duplicates ReconstructionConfig field definitions

### Decision
- Introduce `Displayable` base model in `core/base.py` with lazy-import `.to_widget()`
- Introduce `@map_property` decorator for auto-registered visualization properties
- Auto-generate Qt forms from Pydantic field introspection in `ui/model_widget.py`
- Merge CrystalSystem into CrystallographicEntity base
- Remove manual widget code from ParamPanel, ORPanel, PhasePanel

### Key Constraint
- core/ must NEVER import Qt at module level
- Lazy imports only inside method bodies called at runtime

### Status
- Architecture designed, implementation pending
