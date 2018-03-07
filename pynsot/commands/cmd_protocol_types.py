# -*- coding: utf-8 -*-

"""
Sub-command for Protocol Types.

In all cases ``data = ctx.params`` when calling the appropriate action method
on ``ctx.obj``. (e.g. ``ctx.obj.add(ctx.params)``)

Also, ``action = ctx.info_name`` *might* reliably contain the name of the
action function, but still not sure about that. If so, every function could be
fundamentally simplified to this::

    getattr(ctx.obj, ctx.info_name)(ctx.params)
"""

from __future__ import unicode_literals
import logging

from ..vendor import click
from . import callbacks, types
from .cmd_prototypes import DISPLAY_FIELDS as PROTOTYPE_DISPLAY_FIELDS


# Logger
log = logging.getLogger(__name__)

# Ordered list of 2-tuples of (field, display_name) used to translate object
# field names oto their human-readable form when calling .print_list().
DISPLAY_FIELDS = (
    ('id', 'ID'),
    ('attributes', 'Attributes'),
)

# Fields to display when viewing a single record.
VERBOSE_FIELDS = (
    ('id', 'ID'),
    ('attributes', 'Attributes'),
    ('site', 'Site ID'),
    ('description', 'Description'),
)


# Main group
@click.group()
@click.pass_context
def cli(ctx):
    """
    Protocol Type objects.

    An Protocol Type resource can represent a network protocol type (e.g. bgp, is-is, ospf, etc.)

    Protocol Types can have any number of required attributes as defined below.
    """


# Add
@cli.command()
@click.option(
    '-a',
    '--attributes',
    metavar='ATTRS',
    help='A key/value pair attached to this Protocol Type (format: key=value).  [required]',
    multiple=True,
    callback=callbacks.transform_attributes,
)
@click.option(
    '-e',
    '--description',
    metavar='DESCRIPTION',
    type=str,
    help='The description for this Protocol Type.',
)
@click.option(
    '-n',
    '--name',
    metavar='NAME',
    type=str,
    help='The name of the Protocol Type.  [required]',
)
@click.option(
    '-i',
    '--id',
    metavar='ID',
    help='Unique ID of the Protocol Type being retrieved.',
)
@click.option(
    '-s',
    '--site-id',
    metavar='SITE_ID',
    type=int,
    help='Unique ID of the Site this Protocol Type is under.  [required]',
    callback=callbacks.process_site_id,
)
@click.pass_context
def add(ctx, attributes, description, id, name, site_id):
    """
    Add a new Protocol Type.

    You must provide a Protocol Type name or ID using the UPDATE option.

    When adding a new Protocol Type, you must provide a value for the -n/--name
    option.

    Examples: OSPF, BGP, etc.

    You must also provide attributes, you may specify the -a/--attributes
    option once for each key/value pair.

    You must provide a Site ID using the -s/--site-id option.
    """
    data = ctx.params

    # Required option
    if name is None:
        raise click.UsageError('Missing option "-n" / "--name"')

    # Remove if empty; allow default assignment
    if description is None:
        data.pop('description')

    ctx.obj.add(data)


# List
@cli.group(invoke_without_command=True)
@click.option(
    '-a',
    '--attributes',
    metavar='ATTRS',
    help='A key/value pair attached to this Protocol Type (format: key=value).  [required]',
    multiple=True,
)
@click.option(
    '-e',
    '--description',
    metavar='DESCRIPTION',
    type=str,
    help='Filter by Protocol Type matching this description.',
)
@click.option(
    '-g',
    '--grep',
    is_flag=True,
    help='Display list results in a grep-friendly format.',
    default=False,
    show_default=True,
)
@click.option(
    '-i',
    '--id',
    metavar='ID',
    help='Unique ID of the Protocol Type being retrieved.',
)
@click.option(
    '-n',
    '--name',
    metavar='NAME',
    help='Filter to Protocol Type matching this name.'
)
@click.option(
    '-s',
    '--site-id',
    metavar='SITE_ID',
    help='Unique ID of the Site this Protocol Type is under.  [required]',
    callback=callbacks.process_site_id,
)
@click.pass_context
def list(ctx, attributes, description, grep, id, name, site_id):
    """
    List existing Protocol Typs for a Site.

    You must provide a Site ID using the -s/--site-id option.

    When listing Protocol Types, all objects are displayed by default. You
    optionally may lookup a single Protocol Types by ID using the -i/--id option.
    The ID can either be the numeric ID of the Protocol Type.
    """
    data = ctx.params
    data.pop('delimited')  # We don't want this going to the server.

    # If we provide ID, show more fields
    if id is not None or all([device, name]):
        display_fields = VERBOSE_FIELDS
    else:
        display_fields = DISPLAY_FIELDS

    # If we aren't passing a sub-command, just call list(), otherwise let it
    # fallback to default behavior.
    if ctx.invoked_subcommand is None:
        ctx.obj.list(
            data, display_fields=display_fields,
            verbose_fields=VERBOSE_FIELDS
        )

@list.command()
@click.pass_context
def protocols(ctx, *args, **kwargs):
    """Recursively get all protocols of an Protocol Type."""
    callbacks.list_subcommand(
        ctx, display_fields=PROTOCOL_DISPLAY_FIELDS, my_name=ctx.info_name
    )


# Remove
@cli.command()
@click.option(
    '-i',
    '--id',
    metavar='ID',
    help='Unique ID of the Protocol Type being deleted.',
    required=True,
)
@click.option(
    '-s',
    '--site-id',
    metavar='SITE_ID',
    type=int,
    help='Unique ID of the Site this Protocol Type is under.  [required]',
    callback=callbacks.process_site_id,
)
@click.pass_context
def remove(ctx, id, site_id):
    """
    Remove an Protocol Type.

    You must provide a Site ID using the -s/--site-id option.

    When removing an Protocol Type, you must provide the ID of the Protocol Type using
    -i/--id.

    You may retrieve the ID for an Protocol Type by parsing it from the list of
    Protocol Types for a given Site:

        nsot protocol_types list --site-id <site_id> | grep <protocol_type name>
    """
    data = ctx.params
    ctx.obj.remove(**data)


# Update
@cli.command()
@click.option(
    '-a',
    '--attributes',
    metavar='ATTRS',
    help='A key/value pair attached to this Protocol Type (format: key=value).',
    multiple=True,
    callback=callbacks.transform_attributes,
)
@click.option(
    '-e',
    '--description',
    metavar='DESCRIPTION',
    type=str,
    help='The description for this Protocol Type.',
)
@click.option(
    '-i',
    '--id',
    metavar='ID',
    type=types.NATURAL_KEY,
    help='Unique ID of the Protocol Type being updated.',
    required=True,
)
@click.option(
    '-n',
    '--name',
    metavar='NAME',
    type=str,
    help='The name of the Protocol Type.',
)
@click.option(
    '-s',
    '--site-id',
    metavar='SITE_ID',
    type=int,
    help='Unique ID of the Site this Protocol Type is under.  [required]',
    callback=callbacks.process_site_id,
)
@click.option(
    '--add-attributes',
    'attr_action',
    flag_value='add',
    default=True,
    help=(
        'Causes attributes to be added. This is the default and providing it '
        'will have no effect.'
    )
)
@click.option(
    '--delete-attributes',
    'attr_action',
    flag_value='delete',
    help=(
        'Causes attributes to be deleted instead of updated. If combined with'
        'with --multi the attribute will be deleted if either no value is '
        'provided, or if attribute no longer has an valid values.'
    ),
)
@click.option(
    '--replace-attributes',
    'attr_action',
    flag_value='replace',
    help=(
        'Causes attributes to be replaced instead of updated. If combined '
        'with --multi, the entire list will be replaced.'
    ),
)
@click.pass_context
def update(ctx, attributes, description, id, name, site_id, attr_action):
    """
    Update an Protocol Type.

    You must provide a Site ID using the -s/--site-id option.

    When updating an Protocol Type you must provide the ID (-i/--id) and at least
    one of the optional arguments.

    The -a/--attributes option may be provided multiple times, once for each
    key-value pair.

    When modifying attributes you have three actions to choose from:

    * Add (--add-attributes). This is the default behavior that will add
    attributes if they don't exist, or update them if they do.

    * Delete (--delete-attributes). This will cause attributes to be
    deleted. If combined with --multi the attribute will be deleted if
    either no value is provided, or if the attribute no longer contains a
    valid value.

    * Replace (--replace-attributes). This will cause attributes to
    replaced. If combined with --multi and multiple attributes of the same
    name are provided, only the last value provided will be used.
    """
    if not any([name, attributes, description]):
        msg = 'You must supply at least one of the optional arguments.'
        raise click.UsageError(msg)

    data = ctx.params
    ctx.obj.update(data)
