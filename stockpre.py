# -*- coding: utf-8 -*-
"""stockpre

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1YrecOdq1iYzNRsf3W1TRLqnWcjLRXGxq
"""

!pip install numpy
!pip install tensorflow
!pip install pandas
!pip install --upgrade yfinance
!pip install requests
!pip install textblob
!pip install collections
!pip install matplotlib
!pip install scikit-learn
!pip install datetime
!pip install random
!pip install google-generativeai pandas requests beautifulsoup4
!pip install feedparser

from google.colab import files
uploaded = files.upload()

from google.colab import files
uploaded = files.upload()

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.preprocessing import MinMaxScaler
import random
import tensorflow as tf
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, Dense, LSTM, Conv1D, MaxPooling1D, Dropout, Bidirectional
from tensorflow.keras.callbacks import EarlyStopping
from datetime import date
import google.generativeai as genai
from tensorflow.keras.layers import Multiply, Softmax, Layer

class AttentionReduceSum(tf.keras.layers.Layer):
    def __init__(self, **kwargs):
        super(AttentionReduceSum, self).__init__(**kwargs)

    def call(self, inputs):
        return tf.reduce_sum(inputs, axis=1)

    def compute_output_shape(self, input_shape):
        return (input_shape[0], input_shape[2])


# ------------------- SETUP -------------------
def set_seed(seed=5):
    os.environ['PYTHONHASHSEED'] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
    tf.random.set_seed(seed)

set_seed()

# ------------------- MODEL -------------------
def build_cnn_bilstm_attention_model(input_shape):
    inputs = Input(shape=input_shape)

    x = Conv1D(filters=64, kernel_size=3, activation='relu', padding='same')(inputs)
    x = MaxPooling1D(pool_size=2)(x)
    x = Conv1D(filters=25, kernel_size=3, activation='relu', padding='same')(x)
    x = MaxPooling1D(pool_size=2)(x)

    x = Bidirectional(LSTM(77, return_sequences=True))(x)
    x = Bidirectional(LSTM(64, return_sequences=True))(x)

    attention_scores = Dense(1, activation='tanh')(x)
    attention_weights = Softmax(axis=1)(attention_scores)
    attention_output = Multiply()([x, attention_weights])

    # ❌ Không dùng Lambda
    # context_vector = Lambda(lambda x: tf.reduce_sum(x, axis=1))(attention_output)

    # ✅ Dùng lớp Layer custom thay thế Lambda
    context_vector = AttentionReduceSum()(attention_output)

    x = Dense(80, activation='relu')(context_vector)
    x = Dropout(0.3)(x)
    outputs = Dense(1)(x)

    model = Model(inputs, outputs)
    model.compile(optimizer='adam', loss='mean_squared_error')
    return model


# ------------------- GEMINI SETUP -------------------
genai.configure(api_key="AIzaSyCfxiNhLNM33FkRP6ybJjajqfqvh2bU7AI")
gemini_model = genai.GenerativeModel(model_name="models/gemini-2.0-flash-lite")

def summarize_text(text):
    if pd.isna(text) or text.strip() == "":
        return ""
    prompt = f"Tóm tắt ngắn gọn tin tức sau bằng tiếng Việt:\n\n{text}"
    try:
        response = gemini_model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print("Error with Gemini:", e)
        return "Lỗi tóm tắt"

# ------------------- DATA FETCH -------------------
def fetch_stock_data():
    df = pd.read_csv('/content/F_stock_data.csv')
    df['Date'] = pd.to_datetime(df['Date'])
    return df

# ------------------- MAIN -------------------
if __name__ == '__main__':
    today = date.today()
    stock = 'F'

    df = fetch_stock_data()
    df = df.sort_values('Date')
    df1 = pd.read_excel("tintuc.xlsx")

    # Tóm tắt tin tức
    df1['GeminiSummary'] = df1['Sentiment'].apply(summarize_text)

    # Gộp dữ liệu
    df2 = pd.merge(df, df1, on='Date', how='left')
    df2 = df2.sort_values('Date')
    df2.fillna(0, inplace=True)

    # Chuẩn bị dữ liệu
    features = ['Open', 'High', 'Low', 'Close', 'Volume']
    df2['GeminiSummary'] = df2['GeminiSummary'].astype(str)
    df2['GeminiScore'] = df2['GeminiSummary'].apply(lambda x: len(x))  # proxy encoding
    features.append('GeminiScore')

    new_dataset = df2[['Date'] + features].copy()
    new_dataset.set_index('Date', inplace=True)

    split_date = pd.to_datetime('2024-12-31')
    train_df = new_dataset[new_dataset.index < split_date]
    test_df = new_dataset[new_dataset.index >= split_date]

    scaler = MinMaxScaler()
    scaler.fit(new_dataset.values)
    scaled_train = scaler.transform(train_df)
    scaled_full = scaler.transform(new_dataset)

    window_size = 30
    forecast_horizon = 0
    x_train, y_train = [], []
    for i in range(window_size, len(scaled_train) - forecast_horizon):
        x_train.append(scaled_train[i - window_size:i])
        y_train.append(scaled_train[i + forecast_horizon, features.index('Close')])
    x_train, y_train = np.array(x_train), np.array(y_train)

    # Huấn luyện mô hình
    model = build_cnn_bilstm_attention_model((x_train.shape[1], x_train.shape[2]))
    model.summary()
    early_stop = EarlyStopping(monitor='loss', patience=5, restore_best_weights=True)
    model.fit(x_train, y_train, epochs=50, batch_size=1, callbacks=[early_stop], verbose=0)
    model.save("cnn_bilstm_attention_model.keras")
    # Dự báo
    last_train_part = train_df.values[-window_size:]
    test_values = test_df.values
    total_input = np.concatenate((last_train_part, test_values), axis=0)
    scaled_input = scaler.transform(total_input)

    x_test = []
    for i in range(window_size, len(scaled_input) - forecast_horizon):
        x_test.append(scaled_input[i - window_size:i])
    x_test = np.array(x_test)

    predicted_scaled = model.predict(x_test)
    dummy_full = np.zeros((predicted_scaled.shape[0], len(features)))
    dummy_full[:, features.index('Close')] = predicted_scaled[:, 0]
    predicted_prices = scaler.inverse_transform(dummy_full)[:, features.index('Close')]

    # Chọn số ngày dự báo
    n = 7
    forecast_dates = test_df.index[forecast_horizon:forecast_horizon + n]
    actual_prices = test_df['Close'].values[forecast_horizon:forecast_horizon + n]
    predicted_plot = predicted_prices[:n]

    # Tính xu hướng và tỷ lệ thay đổi
    trend_info = []
    for i in range(n):
        if i == 0:
            prev_price = test_df['Close'].values[forecast_horizon - 1] if forecast_horizon > 0 else actual_prices[0]
        else:
            prev_price = actual_prices[i - 1]

        predicted = predicted_plot[i]
        percent_change = ((predicted - prev_price) / prev_price) * 100 if prev_price != 0 else 0
        trend = "Tăng" if percent_change > 0 else ("Giảm" if percent_change < 0 else "Không đổi")

        trend_info.append({
            "Ngày": forecast_dates[i].strftime('%Y-%m-%d'),
            "Giá dự báo": round(predicted, 2),
            "Xu hướng": trend,
            "Tỷ lệ thay đổi (%)": round(percent_change, 2)
        })

    trend_df = pd.DataFrame(trend_info)
    print("\nDự báo xu hướng giá cổ phiếu:")
    print(trend_df.to_string(index=False))

    # Vẽ biểu đồ
    plt.figure(figsize=(12, 6))
    plt.plot(forecast_dates, actual_prices, label="Thực tế", color="green")
    plt.plot(forecast_dates, predicted_plot, label="Dự báo", linestyle="--", color="purple")
    plt.xlabel("Ngày")
    plt.ylabel("Giá cổ phiếu")
    plt.title(f"Dự báo và so sánh giá cổ phiếu {stock} (CNN + BiLSTM + Attention)")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()

from google.colab import files
files.download("cnn_bilstm_attention_model.keras")

