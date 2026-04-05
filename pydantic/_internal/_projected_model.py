"""Internal implementation details for ``ProjectedModel``.

This module contains the metaclass, marker constant, field-resolution helpers,
and introspection utilities that power ``pydantic.projected_model.ProjectedModel``.

Everything here is private — users should import from ``pydantic.projected_model``
instead.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, NewType, get_args, get_origin

from pydantic import BaseModel, Field, create_model
from pydantic.root_model import _RootModelMetaclass

# ---------------------------------------------------------------------------
# Sentinel type & marker constant
# ---------------------------------------------------------------------------

Projected = NewType('Projected', object)
"""Sentinel type used to mark a field as a direct projection from the source model.

When a field in a ``ProjectedModel`` subclass is annotated with ``Projected``, the
field's type annotation, default value, constraints, description, and all other
``FieldInfo`` metadata are copied from the corresponding field on the source model.
"""

PROJECTION_MARKER: str = '__projected_model_source__'
"""Attribute name stamped onto every class created by ``_ProjectionMeta``.

* On the base ``ProjectedModel`` class itself the value is ``True`` (a truthy
  sentinel meaning "I am the projection origin").
* On concrete projection subclasses the value is the source ``BaseModel`` that
  the projection was derived from.

Using a marker attribute instead of an ``is`` identity check against the
``ProjectedModel`` class removes the circular reference between the helper
functions and the public class.
"""


# ---------------------------------------------------------------------------
# Helper functions — no dependency on ProjectedModel
# ---------------------------------------------------------------------------


def _is_projected_base(base: type) -> bool:
    """Return ``True`` if *base* is a parameterised ``ProjectedModel[X]`` origin.

    Instead of ``get_origin(base) is ProjectedModel`` (which would create a
    circular dependency), we check for the marker attribute that
    ``_ProjectionMeta`` stamps onto every class it creates — including
    ``ProjectedModel`` itself.
    """
    origin = get_origin(base)
    return origin is not None and getattr(origin, PROJECTION_MARKER, None) is not None


def _extract_source_model(namespace: dict[str, Any]) -> type[BaseModel]:
    """Extract the source model type from the class namespace during metaclass construction.

    When a user writes ``class MyView(ProjectedModel[MyModel]): ...``, Python
    stores ``ProjectedModel[MyModel]`` in the ``__orig_bases__`` entry of the new
    class's namespace.  This helper walks those bases, finds the one whose origin
    carries the projection marker, and returns the generic argument (``MyModel``).

    Args:
        namespace: The class namespace dict passed to ``__new__`` of the metaclass.

    Returns:
        The ``BaseModel`` subclass that the projection is derived from.

    Raises:
        TypeError: If none of the bases are a parameterised ``ProjectedModel[...]``,
            meaning the user forgot to specify the source model.
    """
    for base in namespace.get('__orig_bases__', []):
        if _is_projected_base(base):
            (source_model,) = get_args(base)
            return source_model
    raise TypeError('ProjectedModel subclasses must specify ProjectedModel[SourceModel]')


def _get_projection_source(model: type) -> type[BaseModel] | None:
    """Return the source model that *model* projects, or ``None``.

    This is similar to ``_extract_source_model`` but is designed for use *after*
    class creation — it inspects an already-constructed class rather than a raw
    namespace dict.  It is used when resolving nested projections to verify that
    the nested projection's source matches the type of the corresponding field on
    the parent source model.

    The function first tries the fast path — reading the marker attribute
    directly — and falls back to walking ``__orig_bases__`` for classes that were
    not created via ``_ProjectionMeta`` (e.g. plain ``BaseModel`` subclasses).

    Args:
        model: Any type — typically a ``BaseModel`` subclass that may or may not
            be a ``ProjectedModel`` derivative.

    Returns:
        The source ``BaseModel`` subclass if *model* is a ``ProjectedModel``
        subclass, otherwise ``None``.
    """
    # Fast path: the marker attribute is set directly on ProjectedModel subclasses.
    source = getattr(model, PROJECTION_MARKER, None)
    if source is not None and source is not True:
        return source

    # Slow path: walk __orig_bases__ for generic aliases.
    for base in getattr(model, '__orig_bases__', []):
        if _is_projected_base(base):
            (source,) = get_args(base)
            return source
    return None


def _resolve_scalar_field(
    attr_name: str,
    projection_name: str,
    source_model: type[BaseModel],
) -> tuple[type, Any]:
    """Resolve a ``Projected``-annotated field into a ``(type, FieldInfo)`` tuple.

    Looks up *attr_name* in *source_model*'s fields and returns a copy of the
    source field's type annotation and ``FieldInfo``.  A ``deepcopy`` is used so
    that any mutable metadata (constraints, JSON-schema extras, etc.) on the
    source field is not shared with the projected model.

    Args:
        attr_name: The field name as declared in the projection class.
        projection_name: The name of the projection class (used in error messages).
        source_model: The ``BaseModel`` subclass that the projection derives from.

    Returns:
        A ``(annotation, FieldInfo)`` tuple suitable for passing to
        ``pydantic.create_model``.

    Raises:
        ValueError: If *attr_name* does not exist on the *source_model*.
    """
    source_fields = source_model.model_fields
    if attr_name not in source_fields:
        raise ValueError(
            f'Scalar field `{attr_name}` specified in `{projection_name}` '
            f'not found in its source model `{source_model.__name__}`'
        )
    field = source_fields[attr_name]
    return (field.annotation, deepcopy(field))


def _resolve_nested_field(
    attr_name: str,
    attr_value: type[BaseModel],
    projection_name: str,
    source_model: type[BaseModel],
) -> tuple[type, Any]:
    """Resolve a nested projection field into a ``(type, FieldInfo)`` tuple.

    When a field in a projection is annotated with another ``BaseModel`` subclass
    (typically itself a ``ProjectedModel`` subclass), this function validates
    that:

    1. The field name exists on the *source_model*.
    2. If the annotation is itself a ``ProjectedModel`` subclass, its source
       model matches the type of the corresponding field on the *source_model*.
       This prevents accidentally pairing a nested projection with the wrong
       source.

    Args:
        attr_name: The field name as declared in the projection class.
        attr_value: The ``BaseModel`` (or ``ProjectedModel``) subclass used as
            the field's type annotation.
        projection_name: The name of the projection class (used in error
            messages).
        source_model: The ``BaseModel`` subclass that the projection derives
            from.

    Returns:
        A ``(annotation, FieldInfo)`` tuple suitable for passing to
        ``pydantic.create_model``.  The ``FieldInfo`` is a new required field
        (``Field(...)``).

    Raises:
        ValueError: If *attr_name* does not exist on the *source_model*.
        TypeError: If *attr_value* is a ``ProjectedModel`` whose source model
            does not match the type of ``source_model.<attr_name>``.
    """
    source_fields = source_model.model_fields
    if attr_name not in source_fields:
        raise ValueError(
            f'Nested field `{attr_name}` specified in `{projection_name}` '
            f'not found in its source model `{source_model.__name__}`'
        )

    source_field_type = source_fields[attr_name].annotation
    nested_source = _get_projection_source(attr_value)

    if nested_source is not None and nested_source is not source_field_type:
        raise TypeError(
            f'Nested projection `{attr_value.__name__}` projects '
            f'`{nested_source.__name__}`, but `{source_model.__name__}.{attr_name}` '
            f'is of type `{source_field_type.__name__}`'
        )

    return (attr_value, Field(...))


# ---------------------------------------------------------------------------
# Metaclass
# ---------------------------------------------------------------------------


class _ProjectionMeta(_RootModelMetaclass):
    """Metaclass that powers ``ProjectedModel``.

    During class creation, ``_ProjectionMeta`` intercepts the new projection
    subclass, inspects its annotations, resolves each field against the source
    model, and delegates to ``pydantic.create_model`` to build a fully-fledged
    ``BaseModel`` with the correct subset of fields.

    A marker attribute (``__projected_model_source__``) is stamped onto every
    class created by this metaclass.  For the base ``ProjectedModel`` class
    itself the marker is set to a truthy sentinel (``True``); for concrete
    projection subclasses it is set to the source ``BaseModel``.  This allows
    the helper functions above to identify projection classes without holding a
    direct reference to ``ProjectedModel``, breaking the circular dependency.

    See also: https://github.com/pydantic/pydantic/issues/9573
    """

    def __new__(
        cls,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> type[BaseModel]:
        """Dynamically build a ``BaseModel`` subclass from the declared projection fields.

        Each annotation in the projection class is resolved as follows:

        - ``Projected`` — the field's type, default, and metadata are copied from
          the corresponding field on the source model (via
          ``_resolve_scalar_field``).
        - A ``BaseModel`` subclass — treated as a nested (sub-)projection.  The
          field must also exist on the source model, and if the annotation is
          itself a ``ProjectedModel``, its source must match (via
          ``_resolve_nested_field``).
        - Anything else — raises ``TypeError``.  Only the two forms above are
          permitted.

        Annotations whose name starts with ``_`` are silently skipped (these are
        assumed to be private attributes).
        """
        # Bootstrap: the base ProjectedModel class is not a real projection — it
        # has no source model.  We stamp the marker with a truthy sentinel so
        # that _is_projected_base() can recognise it as the projection origin.
        if name == 'ProjectedModel':
            new_cls = super().__new__(cls, name, bases, namespace, **kwargs)
            setattr(new_cls, PROJECTION_MARKER, True)
            return new_cls

        source_model = _extract_source_model(namespace)
        projected_fields: dict[str, Any] = {}

        for attr_name, attr_value in namespace.get('__annotations__', {}).items():
            if attr_name.startswith('_'):
                continue

            if attr_value is Projected:
                projected_fields[attr_name] = _resolve_scalar_field(attr_name, name, source_model)
            elif isinstance(attr_value, type) and issubclass(attr_value, BaseModel):
                projected_fields[attr_name] = _resolve_nested_field(attr_name, attr_value, name, source_model)
            else:
                raise TypeError(
                    f'Field `{attr_name}` on `{name}` must be `Projected` or a Projection subclass, got `{attr_value}`'
                )

        module: str = namespace.get('__module__', source_model.__module__)
        model = create_model(
            name,
            __base__=BaseModel,
            __module__=module,
            **projected_fields,
        )
        # Stamp the marker so that nested projections can be validated.
        setattr(model, PROJECTION_MARKER, source_model)
        return model
