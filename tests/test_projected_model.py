"""Tests for ProjectedModel class and type definitions."""

from typing import Optional

import pytest

from pydantic import BaseModel, Field, ValidationError
from pydantic.projected_model import Projected, ProjectedModel

# ---------------------------------------------------------------------------
# Fixtures: source models used across many tests
# ---------------------------------------------------------------------------


class InnerModel(BaseModel):
    x: int
    y: str


class SourceModel(BaseModel):
    a: int
    b: str
    c: float = 3.14


class NestedSourceModel(BaseModel):
    a: int
    b: str
    c: InnerModel


class DeeplyNestedChild(BaseModel):
    p: int
    q: str


class DeeplyNestedParent(BaseModel):
    child: DeeplyNestedChild
    name: str


class DeeplyNestedRoot(BaseModel):
    parent: DeeplyNestedParent
    value: int


# ---------------------------------------------------------------------------
# Basic projection tests
# ---------------------------------------------------------------------------


def test_projected_model_single_field():
    """A projection selecting a single scalar field should work."""

    class MyProjection(ProjectedModel[SourceModel]):
        a: Projected

    m = MyProjection(a=42)
    assert m.a == 42
    assert m.model_dump() == {'a': 42}


def test_projected_model_multiple_fields():
    """A projection selecting multiple scalar fields should work."""

    class MyProjection(ProjectedModel[SourceModel]):
        a: Projected
        b: Projected

    m = MyProjection(a=1, b='hello')
    assert m.a == 1
    assert m.b == 'hello'
    assert m.model_dump() == {'a': 1, 'b': 'hello'}


def test_projected_model_all_fields():
    """A projection selecting all fields from the source model should work."""

    class MyProjection(ProjectedModel[SourceModel]):
        a: Projected
        b: Projected
        c: Projected

    m = MyProjection(a=1, b='hi', c=2.71)
    assert m.a == 1
    assert m.b == 'hi'
    assert m.c == 2.71
    assert m.model_dump() == {'a': 1, 'b': 'hi', 'c': 2.71}


def test_projected_model_preserves_field_types():
    """Projected fields should inherit the type annotation of the source model."""

    class MyProjection(ProjectedModel[SourceModel]):
        a: Projected
        b: Projected

    # `a` is int in SourceModel — string input should be coerced
    m = MyProjection(a='5', b='test')
    assert m.a == 5
    assert isinstance(m.a, int)


def test_projected_model_validation_error():
    """Projected fields should enforce the source model's type constraints."""

    class MyProjection(ProjectedModel[SourceModel]):
        a: Projected

    with pytest.raises(ValidationError) as exc_info:
        MyProjection(a='not an int')

    errors = exc_info.value.errors(include_url=False)
    assert len(errors) == 1
    assert errors[0]['type'] == 'int_parsing'


def test_projected_model_missing_required_field():
    """Omitting a required projected field should raise a ValidationError."""

    class MyProjection(ProjectedModel[SourceModel]):
        a: Projected
        b: Projected

    with pytest.raises(ValidationError) as exc_info:
        MyProjection(a=1)

    errors = exc_info.value.errors(include_url=False)
    assert any(e['type'] == 'missing' for e in errors)


def test_projected_model_preserves_default():
    """A projected field with a default in the source should keep that default."""

    class MyProjection(ProjectedModel[SourceModel]):
        c: Projected

    m = MyProjection()
    assert m.c == 3.14


# ---------------------------------------------------------------------------
# Nested projection tests
# ---------------------------------------------------------------------------


def test_projected_model_nested():
    """A projection with a nested sub-projection should work."""

    class InnerProjection(ProjectedModel[InnerModel]):
        y: Projected

    class OuterProjection(ProjectedModel[NestedSourceModel]):
        a: Projected
        c: InnerProjection

    m = OuterProjection(a=1, c={'y': 'hello'})
    assert m.a == 1
    assert m.c.y == 'hello'
    assert m.model_dump() == {'a': 1, 'c': {'y': 'hello'}}


def test_projected_model_nested_validation_error():
    """Validation errors inside nested projections should propagate correctly."""

    class InnerProjection(ProjectedModel[InnerModel]):
        x: Projected

    class OuterProjection(ProjectedModel[NestedSourceModel]):
        c: InnerProjection

    with pytest.raises(ValidationError) as exc_info:
        OuterProjection(c={'x': 'not an int'})

    errors = exc_info.value.errors(include_url=False)
    assert len(errors) >= 1
    assert errors[0]['type'] == 'int_parsing'


def test_projected_model_deeply_nested():
    """Projections should work at arbitrary nesting depth."""

    class ChildProjection(ProjectedModel[DeeplyNestedChild]):
        q: Projected

    class ParentProjection(ProjectedModel[DeeplyNestedParent]):
        child: ChildProjection

    class RootProjection(ProjectedModel[DeeplyNestedRoot]):
        parent: ParentProjection

    m = RootProjection(parent={'child': {'q': 'deep'}})
    assert m.parent.child.q == 'deep'
    assert m.model_dump() == {'parent': {'child': {'q': 'deep'}}}


# ---------------------------------------------------------------------------
# model_dump / model_dump_json
# ---------------------------------------------------------------------------


def test_projected_model_dump_json():
    """model_dump_json should produce valid JSON for a projection."""

    class MyProjection(ProjectedModel[SourceModel]):
        a: Projected
        b: Projected

    m = MyProjection(a=1, b='hello')
    json_str = m.model_dump_json()
    assert '"a":1' in json_str or '"a": 1' in json_str
    assert '"hello"' in json_str


def test_projected_model_nested_dump_json():
    """model_dump_json should produce valid JSON for nested projections."""

    class InnerProjection(ProjectedModel[InnerModel]):
        x: Projected

    class OuterProjection(ProjectedModel[NestedSourceModel]):
        c: InnerProjection

    m = OuterProjection(c={'x': 99})
    json_str = m.model_dump_json()
    assert '99' in json_str


# ---------------------------------------------------------------------------
# model_validate / model_validate_json
# ---------------------------------------------------------------------------


def test_projected_model_validate():
    """model_validate should accept a plain dict and return a projection instance."""

    class MyProjection(ProjectedModel[SourceModel]):
        a: Projected
        b: Projected

    m = MyProjection.model_validate({'a': 10, 'b': 'world'})
    assert m.a == 10
    assert m.b == 'world'


def test_projected_model_validate_json():
    """model_validate_json should parse JSON and return a projection instance."""

    class MyProjection(ProjectedModel[SourceModel]):
        a: Projected
        b: Projected

    m = MyProjection.model_validate_json('{"a": 10, "b": "world"}')
    assert m.a == 10
    assert m.b == 'world'


def test_projected_model_validate_nested():
    """model_validate should handle nested projections from dicts."""

    class InnerProjection(ProjectedModel[InnerModel]):
        x: Projected
        y: Projected

    class OuterProjection(ProjectedModel[NestedSourceModel]):
        a: Projected
        c: InnerProjection

    data = {'a': 5, 'c': {'x': 42, 'y': 'nested'}}
    m = OuterProjection.model_validate(data)
    assert m.a == 5
    assert m.c.x == 42
    assert m.c.y == 'nested'


# ---------------------------------------------------------------------------
# model_json_schema
# ---------------------------------------------------------------------------


def test_projected_model_json_schema():
    """model_json_schema should only include projected fields."""

    class MyProjection(ProjectedModel[SourceModel]):
        a: Projected

    schema = MyProjection.model_json_schema()
    assert 'a' in schema.get('properties', {})
    assert 'b' not in schema.get('properties', {})
    assert 'c' not in schema.get('properties', {})


def test_projected_model_json_schema_required():
    """Required fields in the projection should appear in the schema's 'required' list."""

    class MyProjection(ProjectedModel[SourceModel]):
        a: Projected
        b: Projected

    schema = MyProjection.model_json_schema()
    assert 'a' in schema.get('required', [])
    assert 'b' in schema.get('required', [])


def test_projected_model_json_schema_with_default():
    """Fields with defaults should not appear in the schema's 'required' list."""

    class MyProjection(ProjectedModel[SourceModel]):
        c: Projected  # c has default=3.14 in SourceModel

    schema = MyProjection.model_json_schema()
    required = schema.get('required', [])
    assert 'c' not in required


# ---------------------------------------------------------------------------
# Error cases: invalid projection definitions
# ---------------------------------------------------------------------------


def test_projected_model_field_not_in_source():
    """Projecting a field that does not exist in the source model should raise ValueError."""
    with pytest.raises(ValueError, match='not found in its source model'):

        class BadProjection(ProjectedModel[SourceModel]):
            nonexistent: Projected


def test_projected_model_invalid_annotation_type():
    """Using an annotation that is neither Projected nor a BaseModel subclass should raise TypeError."""
    with pytest.raises(TypeError, match='must be `Projected` or a Projection subclass'):

        class BadProjection(ProjectedModel[SourceModel]):
            a: int


def test_projected_model_nested_source_mismatch():
    """A nested projection whose source model doesn't match the source field type should raise TypeError."""

    class WrongInnerProjection(ProjectedModel[SourceModel]):
        a: Projected

    with pytest.raises(TypeError, match='Nested projection'):

        class BadOuter(ProjectedModel[NestedSourceModel]):
            c: WrongInnerProjection


def test_projected_model_nested_field_not_in_source():
    """A nested projection referencing a field not in the source should raise ValueError."""

    class InnerProjection(ProjectedModel[InnerModel]):
        x: Projected

    with pytest.raises(ValueError, match='not found in its source model'):

        class BadOuter(ProjectedModel[NestedSourceModel]):
            nonexistent: InnerProjection


# ---------------------------------------------------------------------------
# model_fields inspection
# ---------------------------------------------------------------------------


def test_projected_model_fields_subset():
    """The projection's model_fields should contain only the projected fields."""

    class MyProjection(ProjectedModel[SourceModel]):
        a: Projected
        b: Projected

    assert set(MyProjection.model_fields.keys()) == {'a', 'b'}


def test_projected_model_fields_types():
    """The projection's model_fields should carry over the correct annotation types."""

    class MyProjection(ProjectedModel[SourceModel]):
        a: Projected
        c: Projected

    assert MyProjection.model_fields['a'].annotation is int
    assert MyProjection.model_fields['c'].annotation is float


# ---------------------------------------------------------------------------
# Equality
# ---------------------------------------------------------------------------


def test_projected_model_equality():
    """Two projection instances with identical data should be equal."""

    class MyProjection(ProjectedModel[SourceModel]):
        a: Projected

    assert MyProjection(a=1) == MyProjection(a=1)
    assert MyProjection(a=1) != MyProjection(a=2)


def test_projected_model_different_projections_not_equal():
    """Projection instances from different projection classes should not be equal,
    even if they carry the same data."""

    class ProjectionA(ProjectedModel[SourceModel]):
        a: Projected

    class ProjectionB(ProjectedModel[SourceModel]):
        a: Projected

    # Different classes → not equal (consistent with BaseModel behaviour)
    assert ProjectionA(a=1) != ProjectionB(a=1)


# ---------------------------------------------------------------------------
# Copy / deepcopy via model_copy
# ---------------------------------------------------------------------------


def test_projected_model_copy():
    """model_copy should produce an equal but distinct instance."""

    class MyProjection(ProjectedModel[SourceModel]):
        a: Projected
        b: Projected

    original = MyProjection(a=1, b='hi')
    copied = original.model_copy()

    assert original == copied
    assert original is not copied


def test_projected_model_deep_copy():
    """model_copy(deep=True) should produce a deep copy."""

    class InnerProjection(ProjectedModel[InnerModel]):
        x: Projected
        y: Projected

    class OuterProjection(ProjectedModel[NestedSourceModel]):
        c: InnerProjection

    original = OuterProjection(c={'x': 1, 'y': 'hello'})
    deep_copied = original.model_copy(deep=True)

    assert original == deep_copied
    assert original is not deep_copied
    assert original.c is not deep_copied.c


# ---------------------------------------------------------------------------
# model_construct (skip validation)
# ---------------------------------------------------------------------------


def test_projected_model_construct():
    """model_construct should create an instance without validation."""

    class MyProjection(ProjectedModel[SourceModel]):
        a: Projected
        b: Projected

    m = MyProjection.model_construct(a='not_validated', b=123)
    # No validation means these keep their original types
    assert m.a == 'not_validated'
    assert m.b == 123


# ---------------------------------------------------------------------------
# Source models with Field metadata
# ---------------------------------------------------------------------------


def test_projected_model_preserves_field_metadata():
    """Field constraints (e.g. gt, max_length) from the source should be preserved."""

    class ConstrainedSource(BaseModel):
        age: int = Field(gt=0, description='Must be positive')
        name: str = Field(max_length=50)

    class AgeProjection(ProjectedModel[ConstrainedSource]):
        age: Projected

    # Valid value
    m = AgeProjection(age=25)
    assert m.age == 25

    # Constraint violation
    with pytest.raises(ValidationError) as exc_info:
        AgeProjection(age=-1)

    errors = exc_info.value.errors(include_url=False)
    assert any(e['type'] == 'greater_than' for e in errors)


def test_projected_model_preserves_field_description_in_schema():
    """Field descriptions from the source should appear in the projection's JSON schema."""

    class DescribedSource(BaseModel):
        value: int = Field(description='An important integer')

    class MyProjection(ProjectedModel[DescribedSource]):
        value: Projected

    schema = MyProjection.model_json_schema()
    assert schema['properties']['value'].get('description') == 'An important integer'


# ---------------------------------------------------------------------------
# Source model with Optional / nullable fields
# ---------------------------------------------------------------------------


def test_projected_model_optional_field():
    """Projecting an Optional field should allow None values."""

    class OptionalSource(BaseModel):
        name: Optional[str] = None

    class MyProjection(ProjectedModel[OptionalSource]):
        name: Projected

    m = MyProjection(name=None)
    assert m.name is None

    m2 = MyProjection()
    assert m2.name is None

    m3 = MyProjection(name='hello')
    assert m3.name == 'hello'


# ---------------------------------------------------------------------------
# Multiple independent projections from the same source
# ---------------------------------------------------------------------------


def test_multiple_projections_from_same_source():
    """Multiple different projections of the same source should be independent."""

    class ProjectionAB(ProjectedModel[SourceModel]):
        a: Projected
        b: Projected

    class ProjectionBC(ProjectedModel[SourceModel]):
        b: Projected
        c: Projected

    m1 = ProjectionAB(a=1, b='hi')
    m2 = ProjectionBC(b='hi', c=2.0)

    assert set(ProjectionAB.model_fields.keys()) == {'a', 'b'}
    assert set(ProjectionBC.model_fields.keys()) == {'b', 'c'}
    assert m1.b == m2.b


# ---------------------------------------------------------------------------
# Projection is a proper BaseModel subclass
# ---------------------------------------------------------------------------


def test_projected_model_is_base_model_subclass():
    """The resulting projection class should be a BaseModel subclass."""

    class MyProjection(ProjectedModel[SourceModel]):
        a: Projected

    assert issubclass(MyProjection, BaseModel)
    assert isinstance(MyProjection(a=1), BaseModel)


# ---------------------------------------------------------------------------
# Projection with private attributes (underscore-prefixed) skipped
# ---------------------------------------------------------------------------


def test_projected_model_skips_private_annotations():
    """Annotations starting with '_' should be silently ignored."""

    class MyProjection(ProjectedModel[SourceModel]):
        a: Projected
        _internal: int  # should be skipped, not treated as a projected field

    m = MyProjection(a=42)
    assert m.a == 42
    assert 'internal' not in MyProjection.model_fields
    assert '_internal' not in MyProjection.model_fields


# ---------------------------------------------------------------------------
# Round-trip: dump → validate
# ---------------------------------------------------------------------------


def test_projected_model_round_trip():
    """Dumping and re-validating should produce an equal instance."""

    class InnerProjection(ProjectedModel[InnerModel]):
        x: Projected
        y: Projected

    class OuterProjection(ProjectedModel[NestedSourceModel]):
        a: Projected
        c: InnerProjection

    original = OuterProjection(a=7, c={'x': 99, 'y': 'round'})
    dumped = original.model_dump()
    restored = OuterProjection.model_validate(dumped)

    assert original == restored


def test_projected_model_json_round_trip():
    """JSON dump → validate_json should produce an equal instance."""

    class MyProjection(ProjectedModel[SourceModel]):
        a: Projected
        b: Projected

    original = MyProjection(a=42, b='json')
    json_str = original.model_dump_json()
    restored = MyProjection.model_validate_json(json_str)

    assert original == restored


# ---------------------------------------------------------------------------
# Edge case: projection with only nested field (no scalar Projected)
# ---------------------------------------------------------------------------


def test_projected_model_only_nested_field():
    """A projection containing only a nested sub-projection (no Projected scalars) should work."""

    class InnerProjection(ProjectedModel[InnerModel]):
        y: Projected

    class OuterProjection(ProjectedModel[NestedSourceModel]):
        c: InnerProjection

    m = OuterProjection(c={'y': 'only nested'})
    assert m.c.y == 'only nested'
    assert m.model_dump() == {'c': {'y': 'only nested'}}


# ---------------------------------------------------------------------------
# Nested projection using a plain BaseModel (not a ProjectedModel)
# ---------------------------------------------------------------------------


def test_projected_model_nested_plain_base_model():
    """Using a plain BaseModel as a nested field annotation should be allowed."""

    class OuterProjection(ProjectedModel[NestedSourceModel]):
        c: InnerModel  # InnerModel is a plain BaseModel, not a ProjectedModel

    m = OuterProjection(c={'x': 1, 'y': 'plain'})
    assert m.c.x == 1
    assert m.c.y == 'plain'


# ---------------------------------------------------------------------------
# Source model with complex field types
# ---------------------------------------------------------------------------


def test_projected_model_list_field():
    """Projecting a field typed as list[int] should preserve the list type."""

    class ListSource(BaseModel):
        items: list[int]
        label: str

    class MyProjection(ProjectedModel[ListSource]):
        items: Projected

    m = MyProjection(items=[1, 2, 3])
    assert m.items == [1, 2, 3]


def test_projected_model_dict_field():
    """Projecting a field typed as dict[str, int] should preserve the dict type."""

    class DictSource(BaseModel):
        mapping: dict[str, int]

    class MyProjection(ProjectedModel[DictSource]):
        mapping: Projected

    m = MyProjection(mapping={'a': 1, 'b': 2})
    assert m.mapping == {'a': 1, 'b': 2}


# ---------------------------------------------------------------------------
# Marker-based architecture tests
# ---------------------------------------------------------------------------


def test_projected_model_has_marker():
    """The base ProjectedModel class should carry the projection marker attribute."""
    from pydantic.projected_model import PROJECTION_MARKER

    assert hasattr(ProjectedModel, PROJECTION_MARKER)
    # The base class marker is a truthy sentinel (True), not a source model.
    assert getattr(ProjectedModel, PROJECTION_MARKER) is True


def test_projected_model_subclass_marker_is_source():
    """Concrete projection subclasses should have the marker set to their source model."""
    from pydantic.projected_model import PROJECTION_MARKER

    class MyProjection(ProjectedModel[SourceModel]):
        a: Projected

    assert getattr(MyProjection, PROJECTION_MARKER) is SourceModel


def test_projected_model_nested_marker_is_source():
    """Nested projection subclasses should also carry the correct marker."""
    from pydantic.projected_model import PROJECTION_MARKER

    class InnerProjection(ProjectedModel[InnerModel]):
        x: Projected

    class OuterProjection(ProjectedModel[NestedSourceModel]):
        a: Projected
        c: InnerProjection

    assert getattr(InnerProjection, PROJECTION_MARKER) is InnerModel
    assert getattr(OuterProjection, PROJECTION_MARKER) is NestedSourceModel


def test_get_projection_source_fast_path():
    """_get_projection_source should resolve via the marker attribute (fast path)."""
    from pydantic.projected_model import _get_projection_source

    class MyProjection(ProjectedModel[SourceModel]):
        a: Projected

    assert _get_projection_source(MyProjection) is SourceModel


def test_get_projection_source_returns_none_for_plain_model():
    """_get_projection_source should return None for a plain BaseModel."""
    from pydantic.projected_model import _get_projection_source

    assert _get_projection_source(SourceModel) is None
    assert _get_projection_source(InnerModel) is None


def test_is_projected_base_on_parameterised_origin():
    """_is_projected_base should identify ProjectedModel[X] as a projected base."""

    from pydantic.projected_model import _is_projected_base

    # ProjectedModel[SourceModel] is a generic alias whose origin is ProjectedModel
    alias = ProjectedModel[SourceModel]
    assert _is_projected_base(alias) is True


def test_is_projected_base_rejects_plain_base_model():
    """_is_projected_base should reject non-projection generic aliases."""

    from pydantic.projected_model import _is_projected_base

    assert _is_projected_base(list[int]) is False
    assert _is_projected_base(BaseModel) is False


def test_plain_base_model_has_no_marker():
    """Plain BaseModel subclasses should not carry the projection marker."""
    from pydantic.projected_model import PROJECTION_MARKER

    assert not hasattr(SourceModel, PROJECTION_MARKER)
    assert getattr(SourceModel, PROJECTION_MARKER, None) is None
