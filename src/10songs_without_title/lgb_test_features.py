# -*- coding: utf-8 -*-
"""
Created on Sun Jun 24 08:54:07 2018

@author: bwhe
"""


import ast
import numpy as np
import pandas as pd
import gc
import pickle
import time

from itertools import repeat


def remove_iteral(sentence):
    return ast.literal_eval(sentence) 

readfile = './cf2xgb_pred1_v6.csv.gz'
savefile = 'cf2xgb_10_pred1_v6.csv.gz'

df_test = pd.read_csv(readfile, usecols=['pid', 'pred', 'scores'], nrows=None)
df_test = df_test.rename(columns={'scores': 'cf_prob'})
w2v_test_pids = df_test.pid.unique()


# save for later prediction
final_df_test = df_test[['pid']]

df_test['pred'] = df_test['pred'].apply(remove_iteral)
df_test['cf_prob'] = df_test['cf_prob'].apply(remove_iteral)

''' convert the list mode to column mode '''
result_test = pd.DataFrame([(tup.pid, pred, cf_prob) for tup in df_test.itertuples() 
                        for pred, cf_prob in zip(tup.pred, tup.cf_prob)])

result_test = result_test.fillna(0)
result_test.columns = ['pid', 'track_uri', 'cf_prob']
del df_test
gc.collect()

''' add relative cf probability score '''
def add_avg_cfscore(data):
    tmp = data.groupby('pid')['cf_prob'].mean().reset_index().rename(columns={'cf_prob':'cf_avg_prob'})
    data = data.merge(tmp, left_on=['pid'], right_on=['pid'], how='left')
    data['cf_rlt_prob'] = data['cf_prob'] / data['cf_avg_prob']
    data = data.drop(['cf_avg_prob'], axis=1)
    return data
start_time = time.time()
result_test = add_avg_cfscore(result_test)
print("average score --- %s seconds ---" % (time.time() - start_time))

''' add song frequency '''
start_time = time.time()
songfreq = pd.read_csv('../data/songfreq.csv.gz')
result_test = result_test.merge(songfreq, left_on=['track_uri'], right_on=['track_uri'], how='left')
print("songfreq merge --- %s seconds ---" % (time.time() - start_time))


''' add album uri '''
start_time = time.time()
with open('../data/song2album.pkl', 'rb') as f:
    song2album = pickle.load(f)
tracks_test = result_test['track_uri'].values
album_uri = [song2album[track] for track in tracks_test]
result_test['album_uri'] = album_uri
print("add album uri --- %s seconds ---" % (time.time() - start_time))

del album_uri, song2album
gc.collect()

''' add track uri '''
start_time = time.time()
with open('../data/song2artist.pkl', 'rb') as f:
    song2artist = pickle.load(f)
artist_uri_test = [song2artist[track] for track in tracks_test]
result_test['artist_uri'] = artist_uri_test
print("add artist uri --- %s seconds ---" % (time.time() - start_time))

del artist_uri_test, song2artist
gc.collect()

pids_test = result_test['pid']


''' add similarity '''
from gensim.models import Word2Vec


model1 = Word2Vec.load('../data/w2v_model1.bin')
model2 = Word2Vec.load('../data/w2v_model2.bin')
model3 = Word2Vec.load('../data/w2v_model3.bin')


with open('../data/song2album.pkl', 'rb') as f:
        song2album = pickle.load(f)

with open('../data/song2artist.pkl', 'rb') as f:
        song2artist = pickle.load(f)

def remove_iteral(sentence):
    return ast.literal_eval(sentence) 


df = pd.read_csv(readfile, usecols=['pid','pos_songs'], nrows=None)
df['pos_songs'] = df['pos_songs'].apply(remove_iteral)

result_test = result_test.merge(df, left_on=['pid'], right_on=['pid'], how='left')

def track_sim(var):
    pos_song = var[0]
    track = var[1]
    try:
        return model1.wv.similarity(str(pos_song), str(track))
    except:
        return 0

def album_sim(var):
    pos_song = var[0]
    track = var[1]
    try:
        return model2.wv.similarity(str(song2album[pos_song]), str(song2album[track]))
    except:
        return 0

def artist_sim(var):
    pos_song = var[0]
    track = var[1]
    try:
        return model3.wv.similarity(str(song2artist[pos_song]), str(song2artist[track]))
    except:
        return 0

def w2v_sim(tup):
    pos_songs = tup.pos_songs 
    track = tup.track_uri
    track_scores = list(map(track_sim, zip(pos_songs, repeat(track))))
    album_scores = list(map(album_sim, zip(pos_songs, repeat(track))))
    artist_scores = list(map(artist_sim, zip(pos_songs, repeat(track))))
    return np.mean(track_scores), np.mean(album_scores), np.mean(artist_scores)

def add_w2v_sim(data):
    track_w2v_sim_arr = []
    album_w2v_sim_arr = []
    artist_w2v_sim_arr = []
    for tup in data.itertuples():
        track_score, album_score, artist_score = w2v_sim(tup)
        track_w2v_sim_arr.append(track_score)
        album_w2v_sim_arr.append(album_score)
        artist_w2v_sim_arr.append(artist_score)
    data['w2v_track_sim'] = track_w2v_sim_arr
    data['w2v_album_sim'] = album_w2v_sim_arr
    data['w2v_artist_sim'] = artist_w2v_sim_arr
    return data

start_time = time.time()
print("Calculate word2vec similarity, this takes a long time, like 1.5h.\n Please be patient...")
result_test = add_w2v_sim(result_test)
print("track w2v similarity --- %s seconds ---" % (time.time() - start_time))


result_test.to_csv(savefile, index=False, compression='gzip')