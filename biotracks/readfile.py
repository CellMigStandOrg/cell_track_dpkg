# import needed libraries
import csv
import os
import xml.etree.ElementTree as ET

import pandas as pd
import xlrd

from .names import (
    X_COORD_NAME, Y_COORD_NAME, FRAME_NAME, OBJECT_NAME, LINK_NAME
)


def read_trackMate(trackMate_file):
    """Read a TrackMate XML file."""

    tree = ET.parse(trackMate_file)
    root = tree.getroot()
    print('>>>')
    print('Reading a TrackMate XML file version {}'.format(
        root.attrib.get('version')))

    ################################
    ### dictionary for the spots ###
    ################################
    spots_dict = {}
    for child in root.find('Model'):
        if child.tag == 'AllSpots':
            spots = child
            for spot_in_frame in spots.getchildren():
                for spot in spot_in_frame.getchildren():
                    # the key
                    SPOT_ID = int(spot.get('ID'))
                    # the value
                    FRAME = int(spot.get('FRAME'))
                    POSITION_X = float(spot.get('POSITION_X'))
                    POSITION_Y = float(spot.get('POSITION_Y'))
                    # insert into dict {frame, x, y}
                    spots_dict[SPOT_ID] = [FRAME, POSITION_X, POSITION_Y]
            break
    print('>>> Found {} unique spots'.format(len(spots_dict)))

    # dictionary into pandas dataframe
    name, extension = os.path.splitext(trackMate_file)
    objects_df = pd.DataFrame([[key, value[0], value[1], value[2]] for key, value in spots_dict.items()], columns=[
        "SPOT_ID", "FRAME", "POSITION_X", "POSITION_Y"])

    ################################
    ### dictionary for the edges ###
    ################################
    edges_dict = {}
    EDGE_ID = 0  # the key
    for child in root.find('Model'):
        if child.tag == 'AllTracks':
            tracks = child
            for track in tracks.getchildren():
                TRACK_ID = int(track.get('TRACK_ID'))
                for edge in track.getchildren():
                    SPOT_SOURCE_ID = int(edge.get('SPOT_SOURCE_ID'))
                    SPOT_TARGET_ID = int(edge.get('SPOT_TARGET_ID'))
                    SOURCE_FRAME = spots_dict.get(SPOT_SOURCE_ID)[0]
                    TARGET_FRAME = spots_dict.get(SPOT_TARGET_ID)[0]
                    # insert {key, value}
                    edges_dict[EDGE_ID] = [TRACK_ID, SPOT_SOURCE_ID,
                                           SPOT_TARGET_ID, SOURCE_FRAME, TARGET_FRAME]
                    EDGE_ID += 1
            break

    print('>>> Found {} unique edges'.format(len(edges_dict)))

    # dictionary into pandas dataframe
    edges_df = pd.DataFrame([[key, value[0], value[1], value[2], value[3], value[4]] for key, value in edges_dict.items()], columns=[
        "EDGE_ID", "TRACK_ID", "SPOT_SOURCE_ID", "SPOT_TARGET_ID", "SOURCE_FRAME", "TARGET_FRAME"])
    # order the df
    ordered_edges_df = edges_df.sort_values(
        ['TRACK_ID', 'SOURCE_FRAME', 'TARGET_FRAME'])
    ordered_edges_df.reset_index(inplace=True)
    # compute the differences across successive rows in frame, spot_source and
    # spot_target
    ordered_edges_df['FRAME_DIFF'] = ordered_edges_df.groupby('TRACK_ID')[
        'SOURCE_FRAME'].diff()
    ordered_edges_df['SPOT_SOURCE_DIFF'] = ordered_edges_df.groupby('TRACK_ID')[
        'SPOT_SOURCE_ID'].diff()
    ordered_edges_df['SPOT_TARGET_DIFF'] = ordered_edges_df.groupby('TRACK_ID')[
        'SPOT_TARGET_ID'].diff()

    # create the 'EVENT' column to be added to the df
    ordered_edges_df['EVENT'] = ['None'] * len(ordered_edges_df)

    for i in range(len(ordered_edges_df)):
        tmp = ordered_edges_df.iloc[i]
        # if difference in frame is 1: no events
        if tmp['FRAME_DIFF'] == 0:
            # if difference of spot source is zero - split event
            if tmp['SPOT_SOURCE_DIFF'] == 0:
                ordered_edges_df.loc[i, 'EVENT'] = 'split'
            elif tmp['SPOT_TARGET_DIFF'] == 0:
                # if difference of spot target is zero - merge event
                ordered_edges_df.loc[i, 'EVENT'] = 'merge'
        # if difference of frame is bigger than 1 - gap event
        elif tmp['FRAME_DIFF'] > 1:
            ordered_edges_df.loc[i, 'EVENT'] = 'gap'
    # shift the event one row up
    ordered_edges_df.EVENT = ordered_edges_df.EVENT.shift(-1)

    ################################
    ### dictionary for the links ###
    ################################
    links_dict = {}
    # initialize id for the link
    LINK_ID = 0

    for track in ordered_edges_df.TRACK_ID.unique():
        event = False
        tmp = ordered_edges_df[
            ordered_edges_df.TRACK_ID == track].reset_index()
        links_dict[LINK_ID] = []
        for index, row in tmp.iterrows():

            if row['EVENT'] == 'None' and event is False:
                links_dict[LINK_ID].append(row['SPOT_SOURCE_ID'])
                links_dict[LINK_ID].append(row['SPOT_TARGET_ID'])
                # if source at row zero is not the same as target at row 1,
                # flag an event
                if tmp.shape[0] > 1:  # if number rows > 1
                    if index == 0 and (tmp.iloc[index].SPOT_TARGET_ID) != (tmp.iloc[index + 1].SPOT_SOURCE_ID):

                        LINK_ID += 1
                        links_dict[LINK_ID] = []
                        event = True

            elif row['EVENT'] == 'split':
                event = True
                LINK_ID += 1
                links_dict[LINK_ID] = []
                links_dict[LINK_ID].append(row['SPOT_SOURCE_ID'])
                links_dict[LINK_ID].append(row['SPOT_TARGET_ID'])

            elif row['EVENT'] == 'merge':
                event = True
                for key, val in links_dict.items():
                    if row['SPOT_SOURCE_ID'] == val[-1]:
                        links_dict[key].append(row['SPOT_TARGET_ID'])
                        links_dict[key].append(row['SPOT_SOURCE_ID'])

            elif row['EVENT'] == 'gap':
                if event is False:
                    links_dict[LINK_ID].append(row['SPOT_SOURCE_ID'])
                    links_dict[LINK_ID].append(row['SPOT_TARGET_ID'])

                elif event is True:
                    for key, val in links_dict.items():
                        if row['SPOT_SOURCE_ID'] == val[-1]:
                            links_dict[key].append(row['SPOT_TARGET_ID'])
                            links_dict[key].append(row['SPOT_SOURCE_ID'])
                LINK_ID += 1
                links_dict[LINK_ID] = []

            elif row['EVENT'] == 'None' and event is True:
                for key, val in links_dict.items():
                    if not val:
                        links_dict[key].append(row['SPOT_SOURCE_ID'])
                        links_dict[key].append(row['SPOT_TARGET_ID'])
                    if row['SPOT_SOURCE_ID'] == val[-1]:
                        links_dict[key].append(row['SPOT_SOURCE_ID'])
                        links_dict[key].append(row['SPOT_TARGET_ID'])

        LINK_ID += 1

    # get only the unique spots
    links_dict_unique = {}
    for key, value in links_dict.items():
        unique_set = set(value)
        links_dict_unique[key] = unique_set
    print('>>> Created {} links'.format(len(links_dict_unique)))

    links_df = pd.DataFrame()
    for key, value in links_dict_unique.items():
        for spot in value:
            links_df = links_df.append([[key, spot]], ignore_index=True)
    links_df.columns = ['LINK_ID', 'SPOT_ID']
    return (objects_df, links_df)


def read_icy(xls_file):
    book = xlrd.open_workbook(xls_file)
    sheet = book.sheet_by_index(0)
    track = None
    obj = 0
    objects, links = [], []
    for i in range(sheet.nrows):
        values = sheet.row_values(i)
        if values[0]:  # track number line
            track = int(values[1])
        elif type(values[2]) is float:  # data line
            objects.append([obj] + values[2:6])
            links.append([track, obj])
            obj += 1
    obj_df = pd.DataFrame(objects, columns=['OBJECT_ID', 't', 'x', 'y', 'z'])
    links_df = pd.DataFrame(links, columns=['LINK_ID', 'OBJECT_ID'])
    return obj_df, links_df


def read_cellprofiler(cp_file, track_dict):
    # pandas dataframe
    cp_df = pd.read_csv(cp_file)
    # dictionary for the objects
    objects_dict = {}
    x = track_dict.get(X_COORD_NAME)
    y = track_dict.get(Y_COORD_NAME)
    frame = track_dict.get(FRAME_NAME)
    obj_id = track_dict.get(OBJECT_NAME)
    # parse the digits used for the tracking settings (e.g. 15)
    digits = x.split('_')[2]
    # sort the dataframe by [track_id, frame]
    track_id = 'TrackObjects_Label_' + digits
    cp_df = cp_df.sort_values([track_id, frame])

    parent_obj_id = 'TrackObjects_ParentObjectNumber_' + digits
    parent_img_id = 'TrackObjects_ParentImageNumber_' + digits
    # create new Object identifiers
    cp_df.reset_index(inplace = True)
    for index, row in cp_df.iterrows():
        objects_dict[index] = [row[frame], row[x], row[y]]

    objects_df = pd.DataFrame([[key, value[0], value[1], value[2]] for key, value in objects_dict.items()], columns=
                              [obj_id, frame, x, y])

    # dictionary for the links
    links_dict = {}
    # initialize id for the link
    LINK_ID = 0

    unique_parent_object = 0
    for track in cp_df[track_id].unique():
        tmp = cp_df[cp_df[track_id] == track]

        for index, row in tmp.iterrows():

            if index == 0:
                links_dict[LINK_ID] = [index]
            else:
                parentImage = row[parent_img_id]
                parentObject = row[parent_obj_id]

                for j, r in tmp.iterrows():
                    if (r.ObjectNumber == parentObject) and (r[frame] == parentImage):
                        unique_parent_object = j
                        break

                if row.ObjectNumber == row[parent_obj_id]:
                    for key, val in links_dict.items():
                        if unique_parent_object == val[-1]:
                            links_dict[key].append(index)
                            break

                else:
                    LINK_ID += 1
                    links_dict[LINK_ID] = []
                    if row[parent_obj_id]!= 0:
                        links_dict[LINK_ID].append(unique_parent_object)
                    links_dict[LINK_ID].append(index)

    print(links_dict)
    links_df = pd.DataFrame()
    for key, value in links_dict.items():
        for object_ in value:
            links_df = links_df.append([[key, object_]])
    links_df.columns = [track_dict.get(LINK_NAME), obj_id]

    return (objects_df, links_df)


def read_file(f, track_dict):
    """Takes file from command line.

    Keyword arguments:
    f -- the file (from command line)
    track_dict -- only needed for some file formats!
    """
    # check for file extension
    if f.endswith('.xls'):
        objects, links = read_icy(f)

    elif f.endswith('.xml'):
        # right now XML associated only to TrackMate, might not be the case in
        # the future
        (objects, links) = read_trackMate(f)
        print('Successfully parsed a TrackMate XML file...')

    if f.endswith('.csv'):
        # if the file is a simple csv, show it
        # open the file and show a quick preview
        print('>>> opening file: {}'.format(f))

        with open(f, 'r') as reader:
            for i in range(20):
                if i == 0:
                    print('>>> header of the file:')
                elif i == 1:
                    print('>>> rest of the file:')
                line = reader.readline()
                print(line)
                objects, links = read_cellprofiler(f, track_dict)
                print('Successfully parsed a CellProfiler CSV file...')
                break


    # show objects and links previews
    print('>>> showing objects dataframe...')
    print(objects.head())
    print('>>> showing links dataframe...')
    print(links.head())

    return {'objects': objects, 'links': links}