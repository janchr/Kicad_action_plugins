#  action_swap_pins.py
#
# Copyright (C) 2018 Mitja Nemec
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#
#

import pcbnew
import os
import re

def swap(board, pad_1, pad_2):

    # get all file paths
    pcb_file = os.path.abspath(str(board.GetFileName()))
    sch_file = os.path.abspath(str(board.GetFileName()).replace(".kicad_pcb", ".sch"))
    cache_file = os.path.abspath(str(board.GetFileName()).replace(".kicad_pcb", "-cache.lib"))

    # get pad numbers
    pad_nr_1 = pad_1.GetPadName()
    pad_nr_2 = pad_2.GetPadName()

    # get module reference
    footprint_reference = pad_2.GetParent().GetReference()

    # get all schematic pages
    all_sch_files = []
    all_sch_files = find_all_sch_files(sch_file, all_sch_files)
    all_sch_files = list(set(all_sch_files))

    # find all schematic pages containing reference
    relevant_sch_files = []
    for page in all_sch_files:
        with open(page) as f:
            current_sch_file = f.read()
        if footprint_reference in current_sch_file:
            relevant_sch_files.append(sch_file)

    # link refernce to symbol
    with open(relevant_sch_files[0]) as f:
        # go through all components
        contents = f.read()
        components = contents.split('$Comp')
        for component in components:
            if footprint_reference in component:
                symbol_name = component.split()[1]
                break

    # load the symbol from cache library
    with open(cache_file) as f:
        contents = f.read()
        symbols = contents.split('ENDDEF')
        for sym in symbols:
            if symbol_name in sym:
                break
    # cleanup everything before DEF
    symbol = sym.split('DEF')[1]

    # grab the pins
    symbol_pins = []
    symbol_fields = symbol.split('\n')
    for field in symbol_fields:
        if field.startswith('X'):
            symbol_pins.append(tuple(field.split()))

    # get number of units
    unit_nr = int(max(symbol_pins, key=lambda item: item[9])[9])

    # construct a list of units, where each unit contains its pins. pin order is the same for all units
    sorted_by_pin_name = sorted(symbol_pins, key=lambda tup: (tup[1], tup[9]))
    pins_by_unit = []
    for i in range(unit_nr):
        pins_by_unit.append([])

    for pin in sorted_by_pin_name:
        pins_by_unit[int(pin[9])-1].append(pin)

    # find which units the pads are connected to
    for pin in symbol_pins:
        if pin[2] == pad_nr_1:
            unit_1 = pin[9]
            break
    for pin in symbol_pins:
        if pin[2] == pad_nr_2:
            unit_2 = pin[9]
            break

    # find pages containing specific units
    for page in relevant_sch_files:
        with open(page) as f:
            current_sch_file = f.read()
            if footprint_reference in current_sch_file:
                components = current_sch_file.split('$Comp')
                for component in components:
                    if footprint_reference in component:
                        for fields in filter(None, component.split('\n')):
                            if fields[0] == 'U':
                                if fields.split()[1] == unit_1:
                                    page_1 = page
                                if fields.split()[1] == unit_2:
                                    page_2 = page

    # swap units in schematics
    with open(page_1) as f:
        current_sch_file = f.read()
        # find location of specific unit
        comp_starts = [m.start() for m in re.finditer('\$Comp', current_sch_file)]
        comp_ends = [m.start() for m in re.finditer('\$EndComp', current_sch_file)]
        for comp in zip(comp_starts, comp_ends):
            data = current_sch_file[comp[0]:comp[1]].split('\n')
            if footprint_reference in data[1]:
                if unit_1 in data[2].split()[1]:
                    # +2 +1 account for splits
                    unit_1_loc = data[2].split()[1].find(unit_1) + comp[0] + len(data[0]) + len(data[1]) + len(data[2].split()[0]) + 2 + 1
                    break
        # swap the unit
        unit_1_sch_file = current_sch_file[:unit_1_loc] + unit_2 + current_sch_file[unit_1_loc+len(unit_1):]
    with open(page_1+'_alt','w') as f:
        f.write(unit_1_sch_file)

    # TODO swap unit 2 in schematics, but if it is in the same file, take care of it


    # swap pins in layout
    pass


def extract_subsheets(filename):
    in_rec_mode = False
    counter = 0
    with open(filename) as f:
        file_folder = os.path.dirname(os.path.abspath(filename))
        file_lines = f.readlines()
    for line in file_lines:
        counter += 1
        if not in_rec_mode:
            if line.startswith('$Sheet'):
                in_rec_mode = True
                subsheet_path = []
        elif line.startswith('$EndSheet'):
            in_rec_mode = False
            yield subsheet_path
        else:
            #extract subsheet path
            if line.startswith('F1'):
                subsheet_path = line.split()[1].rstrip("\"").lstrip("\"")
                if not os.path.isabs(subsheet_path):
                    # check if path is encoded with variables
                    if "${" in subsheet_path:
                        start_index = subsheet_path.find("${") + 2
                        end_index = subsheet_path.find("}")
                        env_var = subsheet_path[start_index:end_index]
                        path = os.getenv(env_var)
                        # if variable is not defined rasie an exception
                        if path is None:
                            raise LookupError("Can not find subsheet: " + subsheet_path)
                        # replace variable with full path
                        subsheet_path = subsheet_path.replace("${", "")\
                                                     .replace("}", "")\
                                                     .replace("env_var", path)

                # if path is still not absolute, then it is relative to project
                if not os.path.isabs(subsheet_path):
                    subsheet_path = os.path.join(file_folder, subsheet_path)

                subsheet_path = os.path.normpath(subsheet_path)
                pass


def find_all_sch_files(filename, list_of_files):
    list_of_files.append(filename)
    for sheet in extract_subsheets(filename):
        seznam = find_all_sch_files(sheet, list_of_files)
        list_of_files = seznam
    return list_of_files


def main():
    board = pcbnew.LoadBoard('swap_units_test.kicad_pcb')
    mod = board.FindModuleByReference('U1')
    pads = mod.Pads()
    for pad in pads:
        if pad.GetPadName() == u'1':
            pad1 = pad
        if pad.GetPadName() == u'7':
            pad2 = pad
    pass
    swap(board, pad1, pad2)


# for testing purposes only
if __name__ == "__main__":
    main()