"""
Explain the bit settings from a dup_diff structure.
"""
from src.router.shared.models.doi_register import describe_bit_settings


def print_output(title, list_of_tuples):
    print(f"\n\n*** {title} ***\n")
    print("Bit-num | Rating | Description")
    for bit, desc, rating in list_of_tuples:
        print("{:2d} | {:1d} | {} ".format(bit, rating, desc))
    print("----------------------------------------------")


while True:
    bit_field_value = input("\n\n** Enter bit-field value:")
    if bit_field_value == "":
        break

    bit_field_value = int(bit_field_value)

    set_on, set_off = describe_bit_settings(bit_field_value, True)

    print_output("Bits set ON", set_on)
    print_output("Bits not set", set_off)

