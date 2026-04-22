"""
Describe a dup_diff structure - to show what has changed
"""
from src.router.shared.models.doi_register import describe_differences


def print_output(title, diff_dict):
    """
    diff_dict: {
                "old_date": Date of first notification
                "new": [List of field descriptions present in new notification but not in old],
                "lost": [List of field descriptions that were present in old, but are not in new],
                "increased": [List describing increases in counts],
                "decreased": [List describing decreases in counts],
                "add_bits": Int: bit-field with bits set on for new fields or where counts have increased
                }
    :param title:
    :param diff_dict:
    :return:
    """
    print(f"\n\n*** {title} ***")
    print(f"\nFirst notification date: {diff_dict['old_date']}")
    for key in ["new", "lost", "increased", "decreased"]:
        print(f"\n** {key.upper()} **")
        for v in diff_dict[key]:
            print(f" * {v} ")
    print("----------------------------------------------")


while True:
    diff_dict_value = input("\n\n** Enter Diff-dict on ONE line (i.e. flattened):")
    if diff_dict_value == "":
        break

    diff_dict_value = eval(diff_dict_value)

    differences_dict = describe_differences(diff_dict_value)

    print_output("Differences", differences_dict)

