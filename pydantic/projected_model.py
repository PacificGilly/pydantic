"""ProjectedModel class and type definitions.

Projected models provide a declarative way to create subset views of existing Pydantic
models — selecting only the fields you need while preserving their type annotations,
validators, defaults, constraints, and other field metadata from the source model.

This is useful for patterns such as:

- **API response shaping**: Return only the fields relevant to a particular endpoint,
  without manually redefining types and constraints.
- **GraphQL-style field selection**: Let callers declare exactly which fields they need
  from a larger domain model.
- **DTO / read-model patterns**: Derive lightweight Data Transfer Objects from rich
  domain models without duplicating schema definitions.

The main public symbols are:

- [`ProjectedModel`][pydantic.projected_model.ProjectedModel]: The generic base class
  that projections inherit from. Parameterised with the source `BaseModel` to project.
- [`Projected`][pydantic.projected_model.Projected]: A sentinel type used to annotate
  scalar fields that should be carried over from the source model as-is.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel
from pydantic._internal._projected_model import (
    Projected as Projected,
)
from pydantic._internal._projected_model import (
    _ProjectionMeta,
)

T = TypeVar('T', bound=BaseModel)

__all__ = ('ProjectedModel', 'Projected')


class ProjectedModel(Generic[T], BaseModel, metaclass=_ProjectionMeta):
    """A generic base class for creating *projected* (subset) views of Pydantic models.

    ``ProjectedModel`` lets you declaratively select a subset of fields from an
    existing ``BaseModel`` without redefining their types, defaults, or
    constraints.  The resulting class **is** a standard ``BaseModel`` — it
    supports validation, serialisation (``model_dump``, ``model_dump_json``),
    JSON Schema generation, and everything else you would expect.

    To create a projection:

    1. Subclass ``ProjectedModel[SourceModel]``, where *SourceModel* is the
       ``BaseModel`` you want to project from.
    2. Annotate each field you want to include with the ``Projected`` sentinel
       type.  The field's full definition (type, default value, ``Field``
       constraints, description, alias, etc.) is deep-copied from the source
       model so that changes to either model do not affect the other.
    3. For nested model fields, annotate with another ``ProjectedModel`` subclass
       (or any ``BaseModel`` subclass) instead of ``Projected``.

    Notes:
        - Only fields annotated with ``Projected`` or a ``BaseModel`` subclass
          are allowed.  Specifying a plain Python type (e.g. ``int``, ``str``)
          will raise a ``TypeError``.
        - If a field name in the projection does not exist on the source model,
          a ``ValueError`` is raised at class-creation time.
        - For nested projections, if the nested ``ProjectedModel`` targets a
          different source model than the type of the corresponding field on the
          parent source, a ``TypeError`` is raised at class-creation time.
        - Field metadata — including ``Field`` constraints (``ge``,
          ``max_length``, etc.), ``description``, ``alias``, ``default``, and
          ``default_factory`` — is carried over via ``deepcopy`` so that
          projected fields behave identically to their source counterparts.

    Examples:
        Simple projection — selecting a subset of fields:

        ```python
        from pydantic import BaseModel
        from pydantic.projected_model import Projected, ProjectedModel

        class User(BaseModel):
            id: int
            name: str
            email: str

        class UserSummary(ProjectedModel[User]):
            id: Projected
            name: Projected

        user = UserSummary(id=1, name='Alice')
        print(user.model_dump())
        #> {'id': 1, 'name': 'Alice'}
        ```

        Field metadata is preserved (defaults, constraints, etc.):

        ```python
        from pydantic import BaseModel, Field
        from pydantic.projected_model import Projected, ProjectedModel

        class Product(BaseModel):
            sku: str
            price: float = Field(gt=0, description='Retail price')
            currency: str = 'USD'

        class ProductPrice(ProjectedModel[Product]):
            price: Projected
            currency: Projected

        item = ProductPrice(price=9.99)  # currency defaults to 'USD'
        print(item.model_dump())
        #> {'price': 9.99, 'currency': 'USD'}
        ```

        Validation still applies — invalid data is rejected:

        ```python
        from pydantic import BaseModel, Field, ValidationError
        from pydantic.projected_model import Projected, ProjectedModel

        class Item(BaseModel):
            name: str
            quantity: int = Field(ge=0)

        class ItemView(ProjectedModel[Item]):
            quantity: Projected

        try:
            ItemView(quantity=-1)
        except ValidationError as e:
            print(e.error_count())
            #> 1
        ```

        Nested projections — projecting models that contain other models:

        ```python
        from pydantic import BaseModel
        from pydantic.projected_model import Projected, ProjectedModel

        class Address(BaseModel):
            street: str
            city: str
            zip_code: str

        class Customer(BaseModel):
            id: int
            name: str
            address: Address

        class AddressBrief(ProjectedModel[Address]):
            city: Projected

        class CustomerBrief(ProjectedModel[Customer]):
            name: Projected
            address: AddressBrief

        brief = CustomerBrief(name='Bob', address={'city': 'Springfield'})
        print(brief.model_dump())
        #> {'name': 'Bob', 'address': {'city': 'Springfield'}}
        ```
    """
