"""Short messages the browser scripts show (quizzes). English is built into quiz.js; these are the Kiswahili versions."""

import json

SW = {
    "checkFailed": "Hatukuweza kukagua jibu hilo. Tafadhali jaribu tena.",
    "offline": "Huna intaneti? Angalia mtandao wako kisha ujaribu tena.",
    "answered": "Umejibu {0} kati ya {1}",
    "saveFailed": "Hatukuweza kuhifadhi alama zako. Tafadhali jaribu tena.",
    "gradeFailed": "Hatukuweza kusahihisha mtihani wako. Tafadhali jaribu tena.",
    "passedQuiz": "Umefaulu maswali haya{0}. Unaweza kumaliza somo.",
    "gotQuiz": "Umepata {0} kati ya {1} ({2}%). Umefaulu maswali!",
    "gotExam": "Umepata {0} kati ya {1} ({2}%). Umefaulu mtihani!",
    "retry": "Umepata {0} kati ya {1} ({2}%). Unahitaji {3}%. Jaribu tena!",
    "correct": "Sahihi",
    "review": "Pitia",
    "outOf": "{0} kati ya {1} sahihi",
    "examPass": "Hongera, umefaulu mtihani huu wa kozi! Telemka chini uweke kama umekamilika.",
    "examFail": "Unahitaji {0}% kufaulu. Pitia maswali hapa chini, rudia masomo usiyoyajua vizuri, kisha ujaribu tena.",
    "answeredExam": "Umejibu {0} kati ya {1}",
}


def js_json(language):
    return json.dumps(SW if (language or "en").startswith("sw") else {})
