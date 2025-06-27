"""
To run this script, you need to install the following libraries:
`$ pip install genson pyyaml`
"""
import json
import yaml
from argparse import ArgumentParser

from genson import SchemaBuilder


def add_example(schema, example):
    """
    Recursively adds example values to the schema.
    """
    if schema.get("type") == "array" and "items" in schema:
        if isinstance(example, list) and example:
            add_example(schema["items"], example[0])
    if schema.get("type") == "object" and "properties" in schema:
        for key, subschema in schema["properties"].items():
            if example.get(key):
                value = example[key]
                if not isinstance(value, (dict, list)):
                    subschema["example"] = value
                if isinstance(value, dict):
                    add_example(subschema, value)
                elif isinstance(value, list) and value and isinstance(value[0], dict):
                    add_example(subschema["items"], value[0])


def gen_schema(data):
    builder = SchemaBuilder()
    builder.add_object(data)
    schema = builder.to_schema()
    add_example(schema, data)
    return schema


def json_schema_to_yaml(json_schema=None, json_path=None, yaml_path=None):
    if not json_schema:
        if not json_path:
            raise ValueError("json_schema or json_path must be specified.")
        with open(json_path, "r", encoding="utf-8") as f:
            json_schema = json.load(f)
    yaml_str = yaml.dump(json_schema, sort_keys=False)
    if yaml_path:
        with open(yaml_path, "w", encoding="utf-8") as f:
            f.write(yaml_str)
    else:
        print(yaml_str)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "-i", "--input", type=str, required=True, help="Input JSON file path"
    )
    parser.add_argument("-o", "--output_json", type=str, help="Output JSON schema file path")
    parser.add_argument("-y", "--output_yaml", type=str, help="Output YAML schema file path")

    args = parser.parse_args()
    input_fp = args.input
    output_json = args.output_json
    output_yaml = args.output_yaml

    with open(input_fp) as f:
        data = json.load(f)
    schema = gen_schema(data)

    if output_yaml or (not output_yaml and not output_json):
        # If no output JSON is specified, default to YAML output
        output_yaml = output_yaml or "schema.yml"
        json_schema_to_yaml(json_schema=schema, yaml_path=output_yaml)
    else:
        with open(output_json, "w") as f:
            json.dump(schema, f, ensure_ascii=False, indent=2)
    print(f"Schema generated and saved to {output_json or output_yaml}")
