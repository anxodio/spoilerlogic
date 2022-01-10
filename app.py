import os
import random
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Set, List

from chalice import Chalice, Cron
from dotenv import load_dotenv
import requests
from requests_oauthlib import OAuth1
import imgkit


SOLUTION_URL = "https://vilaweb.cat/paraulogic/?solucions="
DIEC_URL = "https://vilaweb.cat/paraulogic/?diec="
TWITTER_URL = "https://api.twitter.com/2/tweets"
DIEC_COPYRIGHT = "<br /><br /><span>© Institut d'Estudis Catalans</span>"
BIG_WORD_MIN_LENGTH = 6
START_HOUR = 9


load_dotenv()
app = Chalice(app_name="spoilogic")


@dataclass
class Word:
    key: str
    words: str
    score: int
    is_tuti: bool

    @staticmethod
    def build(key: str, words: str, today_letters: Set[str]) -> "Word":
        score = len(key) if len(key) > 4 else len(key) - 2
        is_tuti = today_letters.issubset(set(key))
        if is_tuti:
            score += 10
        return Word(key, words, score, is_tuti)


@app.route("/")
def index():
    word = get_current_word()
    return {"Current word": word.key}


@app.route("/tweet")
def tweet():
    word = get_current_word()
    created_id = make_tweet(word)
    print(created_id)
    # By the moment, we avoid spamming :D
    # paraulogic_tweets = search_last_paraulogic_tweets()
    # reply_to_paraulogic_tweets(paraulogic_tweets, created_id)


@app.route("/solutions")
def tweet_all_solutions():
    solutions = download_solutions()["paraules"].keys()
    tweet_solution_image(solutions)


@app.route("/tutis")
def tweet_tutis():
    solution = download_solutions()
    tweet_amount_of_tutis(solution)


@app.schedule(Cron("*/20", "8-21", "*", "*", "?", "*"))
def scheduled_tweet(event):
    tweet()


@app.schedule(Cron("0", "22", "*", "*", "?", "*"))
def scheduled_solutions(event):
    tweet_all_solutions()


@app.schedule(Cron("30", "7", "*", "*", "?", "*"))
def scheduled_tutis():
    tweet_tutis()


def get_current_word() -> Word:
    raw_solutions = download_solutions()
    actual_position = get_position_by_datetime()
    raw_word = get_nth_big_word(raw_solutions["paraules"].keys(), actual_position)
    return Word.build(
        raw_word, raw_solutions["paraules"][raw_word], set(raw_solutions["lletres"])
    )


def download_solutions() -> dict:
    return requests.get(
        SOLUTION_URL + "{:%Y-%m-%d}".format(datetime.now()),
        headers={"User-Agent": "Mozilla/5.0"},
    ).json()


def get_position_by_datetime() -> int:
    # Every twenty minutes position increments by one
    now = datetime.now()
    start_datetime = datetime(now.year, now.month, now.day, START_HOUR, 0, 0)
    return (now - start_datetime).seconds // 1200


def get_nth_big_word(words: List[str], position: int) -> str:
    big_words = [word for word in words if len(word) >= BIG_WORD_MIN_LENGTH]
    return big_words[position]


def get_amount_of_tutis(raw_solutions: dict) -> int:
    today_words = map(lambda word: Word.build(
        word, raw_solutions["paraules"][word], set(raw_solutions["lletres"])
    ), raw_solutions["paraules"])
    return len([w for w in today_words if w.is_tuti])


def get_twitter_auth() -> OAuth1:
    return OAuth1(
        os.getenv("TWITTER_API_KEY"),
        client_secret=os.getenv("TWITTER_API_SECRET"),
        resource_owner_key=os.getenv("TWITTER_OAUTH_ACCESS_TOKEN"),
        resource_owner_secret=os.getenv("TWITTER_OAUTH_ACCESS_TOKEN_SECRET"),
    )


def make_tweet(word: Word) -> int:
    text = word.key.upper()
    if word.is_tuti:
        text += "\n\n 🆃🆄🆃🅸"

    definition_html = get_diec_definition_html(word)
    media_id = upload_string_to_image(definition_html)

    auth = get_twitter_auth()
    response = requests.post(
        TWITTER_URL,
        auth=auth,
        json={"text": text, "media": {"media_ids": [str(media_id)]}},
    )
    return response.json()["data"]["id"]


def get_diec_definition_html(word: Word) -> str:
    definition_word = word.words.split(" ")[0]

    return (
        requests.get(
            DIEC_URL + definition_word,
            headers={
                "User-Agent": "Mozilla/5.0",
            },
        ).json()["d"]
        + DIEC_COPYRIGHT
    )


def upload_string_to_image(string: str) -> int:
    config = imgkit.config()
    if os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        config = imgkit.config(wkhtmltoimage="./bin/wkhtmltoimage")
    binary_img = imgkit.from_string(
        string, False, config=config, options={"width": "500"}
    )

    auth = get_twitter_auth()
    response = requests.post(
        "https://upload.twitter.com/1.1/media/upload.json",
        auth=auth,
        files={"media": binary_img},
    )
    return response.json()["media_id"]


def search_last_paraulogic_tweets() -> List[dict]:
    auth = get_twitter_auth()
    twenty_minutes_ago = datetime.now() - timedelta(minutes=20)
    response = requests.get(
        "https://api.twitter.com/2/tweets/search/recent",
        auth=auth,
        params={
            "query": "paraulogic -is:retweet -(@paraulogic is:reply)",
            "start_time": twenty_minutes_ago.isoformat(timespec="seconds") + "Z",
        },
    )
    return response.json()["data"]


def reply_to_paraulogic_tweets(tweet_list: List[dict], created_id: int) -> None:
    emoji_replies = "😅😇🙃🥰😘😛😝😜🤪😎🤩😏🥺🤯😳😱😨😰😥🤗🤔🤭🤫😶😬🙄😯😵🤐🥴😈👻🤖🙀👋🖖🤟🤘🤙👆✊🙌💪"
    random_emojis = "".join(random.sample(emoji_replies, len(emoji_replies)))
    auth = get_twitter_auth()
    for i, tweet in enumerate(tweet_list):
        response = requests.post(
            TWITTER_URL,
            auth=auth,
            json={
                "text": random_emojis[i],
                "reply": {"in_reply_to_tweet_id": tweet["id"]},
                "quote_tweet_id": created_id,
            },
        )
        print(response.text)


def tweet_solution_image(words: List[str]) -> int:
    media_id = upload_string_to_image(", ".join(words).upper())
    text = "Totes les paraules d'avui!"

    auth = get_twitter_auth()
    response = requests.post(
        TWITTER_URL,
        auth=auth,
        json={"text": text, "media": {"media_ids": [str(media_id)]}},
    )
    return response.json()["data"]["id"]


def tweet_amount_of_tutis(raw_solutions: dict) -> None:
    amount_of_tutis = get_amount_of_tutis(raw_solutions)
    sentence = ('només hi trobareu un tuti', f'hi podreu trobar {amount_of_tutis} tutis')[amount_of_tutis > 1]

    auth = get_twitter_auth()
    response = requests.post(
        TWITTER_URL,
        auth=auth,
        json={"text": f'Bon dia! 👋\n\nAl Paraulògic d\'avui {sentence}. Bona sort!'},
    )
    print(response.text)


if __name__ == "__main__":
    # tweet()
    # tweet_all_solutions()
    # print(search_last_paraulogic_tweets())
    print(get_current_word().word)
