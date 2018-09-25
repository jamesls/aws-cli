# Server side auto-completion

SEP              | Metadata
---------------- | -------------
**CLIP Number**  | 0001
**Author**       | James Saryerwinnie
**Status**       | Proposed
**Created**      | 2018-09-21

## Abstract

The AWS CLI allows you to auto complete service names, operation names, and top
level parameters.  This CLIP adds the ability to auto complete parameter values
by making service API calls and extracting values from the response data.
It also allows the auto completion to be specified declaratively in JSON files.


## Motivation

The number of AWS CLI commands continues to grow year over year.  In addition
to new services, there's new operations and parameters being added to existing
services.  By offering more auto completion, we can streamline the user
experience for CLI customers by reducing the total time needed to invoke
a command.  Auto completion of resource values also reduces errors from
mistyping.

The long term goal of auto completion is that anything that can be
auto completed should be auto completed.  While this SEP only deals with
server side auto completion, there are additional gaps in the CLI's
auto completion including:

* `--query` values
* Enum values for parameters
* Shorthand syntax
* JSON parameters
* Filename completion for `file://`


## Specification

There are several terms used in the specification of this SEP.

Suppose a user has entered a partial CLI command:

```
$ aws cloudformation delete-stack --stack-name <TAB>
```

The **User Operation** is `cloudformation.DeleteStack`.  This is the operation
that the CLI user would like to execute.  The `--stack-name` is the **User
Parameter**.  This is the name of the top level parameter for which the user
would like completion suggestions.  In order to retrieve a list of valid
stack names the user can delete, we must make a `cloudformation.ListStacks`
API call.  This is referred to as the **Completion Operation**.  And finally
we must take the API response and extract a list of stack names.  We can
do this by evaluation the JMESPath expression `Stacks[].StackName` against
the response for `cloudformation.ListStacks`.  This expression is referred
to as the **Completion Expression**.

This scope of this SEP focuses on context free server side auto-completion.
This means:

* The completion values for a given parameter are independent of any existing
  input parameters.
* There is a 1-1 mapping of parameter name to completion operation.

This keeps the specification simple, but it has known limitations.  With context
free completion, it is possible to offer completion suggestions that aren't
valid.

This SEP also does not address implementation details.  It focuses solely on
how to model server side auto completion and how the AWS CLI can consume this
data.

### Schema for auto complete

The data for auto completing resources will use the existing
botocore loaders and the same file structure used for service models,
paginators, and waiters.  There will be a new `completions-1.json` file
that will be placed in `data/<service>/<api-version>/completions-1.json`.
This file will have the following structure:

```json
{
  "version": "1.0",
  "operations": {...},
  "resources": {...}
}
```

```json

```

The ``version`` key identifies the version of the completion file.
This CLIP describes the format for version "1.0" of the file.
There are two top level keys, `operations` and `resources`.

Auto completion is performed per operation.  Given an operation and
a parameter, the `completions-1.json` file specifies what API call
to make to offer completion suggestions.
This is described by the `operations` key:


```json
{
  "operations": {
    "<operation-name>": {
      "<member-name>": {
        "resourceName": "<string>",
        "resourceIdentifier": "<string>",
      }
    }
  }
}
```

The `<operation-name>` must exactly match a name in the `operations` mapping
of the corresponding `service-2.json` file for the service.
The `<member-name>` must exactly match a name of a member in the input
structure for an operation.  For a given operation and member name, there are
two required parameters, the `resourceName` and `resourceIdentifier`.
The `resourceName` must match a key in the `resources` map of the
`completions-1.json` file.  A resource can have one or more identifiers.
The `resourceIdentifier` specifies which identifier of the resource to use.

The `resources` top level key has this structure:


```json
{
  "resources": {
    "<resource-name>": {
      "operation": "<operation-name>",
      "<resource-identifier>": {
        "<identifier-name>": "<jmespath-expression>"
      }
    }
  }
}
```

The `<resource-name>` is an arbitrary name.  The operation denotes
the name of the service operation to invoke in order to retrieve
the identifiers for the resource.  This must match a key in the
`operations` map of the `service-2.json` file.  The operation is
assumed to be an operation in the same service.  Cross service
operations are not supported.

The resource identifier map represents a map of arbitrary resource
identifiers to JMESPath expressions.  The JMESPath expression
describes how to extract out the specific resource identifier given
a service response.

### Algorithm

The input to the algorithm is a service, an operation, and a top level
parameter name.  The output is a list of values suitable for the
parameter. Below is pseudocode for how to use the `completions-1.json`
file:


```python
def autocomplete(service, operation, parameter):
    completions = load_completions_json_file(service)
    known_operations = completions['operations']
    completion_info = completions['operations'][operation][parameter]
    if not completion_info:
        # No autocompletion defined for this operation/parameter.
        return []
    resource_name = completion_info['resourceName']
    resource_identifier	= completion_info['resourceIdentifier']
    resource = completions[resource_name]

    autocomplete_operation = resource[operation]
    jp_expression = resource['resourceIdentifier'][resource_identifier]

    response = make_aws_api_call(service, autocomplete_operation)
    results = jmespath.search(jp_expression, response)
    return results

```


### Worked example

Suppose we have a `completions-1.json` file for cloudformation:

```json
{
  "operations": {
    "DeleteStack": {
      "StackName": {
        "resourceName": "Stack", 
        "resourceIdentifier": "Name"
      }
    }, 
  },
  "resources": {
    "Stack": {
      "operation": "DescribeStacks", 
      "resourceIdentifier": {
        "Name": "Stacks[].StackName"
      }
    }
  }
}
```

Now suppose a CLI User has entered the following in their shell:

```
$ aws cloudformation delete-stack --stack-name <TAB>
```

This is a trace through the algorithm described above:


1. Check if there's auto complete information for the service, operation
   and parameter.  In this example, we see that there's a `completions-1.json`
   file for cloudformation, the `DeleteStack` is in the `operations` map,
   and that `StackName` is in the `DeleteStack` map.
2. Lookup the resourceName in the `resources` map.  The `resourceName` in this
   example is `Stack`.
3. Lookup operation name for the `Stack` resource, which is `DescribeStacks`.
4. Make an `DescribeStacks` call to the cloudformation API.
5. Lookup the JMESPath expression that corresponds to the `resourceIdentifier`
   of `Name`.
6. Evaluate the `Stacks[].StackName` on the response from `DescribeStacks`.
   The result is returned to the user as auto completion suggestions.


## Rationale

This spec is taken from a working implementation of the
[aws-shell](http://github.com/awslabs/aws-shell).  This gives confidence
that the schema is able to describe basic server side auto-complete.  There
are 11 services in the aws shell today that offer server side auto complete.
While the context-free format proposed here has the known limitation that
some of the completion suggestions will be invalid, it has the benefit that
a majority of the auto completion files can be autogenerated from either
a `resources-1.json` file or a `service-2.json` file.  The `resources-1.json`
file allows us to directly generate the `completions-1.json` file due to
resources being explicitly modeled.  Using a set of heuristics, we can
auto generate more completions from the `service-2` file, with the caveat
that they will need to be reviewed for accuracy.

There is an alternative version of this SEP that describes a schema
for context sensitive auto completion.  This can more accurately describe
how to auto complete resources values, but is more complex to write and
implement.
