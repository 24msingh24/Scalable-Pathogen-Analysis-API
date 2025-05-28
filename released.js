import http, { get } from "k6/http";
import { check, sleep } from "k6";
import { Counter} from "k6/metrics";
import { covid1 } from './images.js';

const ENDPOINT = __ENV.ENDPOINT;
const params = {
    headers: {
        'Content-Type': 'application/json',
    },
};

const errors = new Counter("errors");
const attempted = new Counter("analyses_attempted");
const analysisCorrect = new Counter("analysis_correct");

export const options = {
    scenarios: {
        normal_circumstances: {
            executor: 'ramping-vus',
            startVUs: 0,
            stages: [
            { duration: '1m', target: 5 },
            { duration: '3m', target: 15 },
            { duration: '1m', target: 0 },
            ],
            exec: 'Normal_Circumstance',
        },
        curiosity_killed_server: {
            executor: 'ramping-vus',
            startVUs: 0,
            stages: [
                { duration: '2m', target: 20 },
                { duration: '2m', target: 45 },
                { duration: '2m', target: 80 },
                { duration: '2m', target: 50 },
                { duration: '2m', target: 0 },
            ],
            exec: 'Curiosity_Killed',
            startTime: '10m', // Give normal tests time to complete analysis for use in later tests.
        },
        epidemic_early_stages: {
            executor: 'ramping-vus',
            startVUs: 0,
            stages: [
                { duration: '2m', target: 40 },
                { duration: '4m', target: 60 },
                { duration: '1m', target: 0 },
            ],
            exec: 'Epidemic_Early',
            startTime: '24m', // Time for curiosity test to scale down.
        },
        epidemic_peak: {
            executor: 'ramping-vus',
            startVUs: 0,
            stages: [
                { duration: '2m', target: 40 },
                { duration: '1m', target: 60 },
                { duration: '4m', target: 80 },
                { duration: '2m', target: 0 },
            ],
            exec: 'Epidemic_Peak',
            startTime: '35m',
        },
		cool_down: {
			executor: 'ramping-vus',
			startVUs: 0,
			stages: [
				{ duration: '2m', target: 1 },
				{ duration: '2m', target: 0 },
			],
			exec: 'Cool_Down',
			startTime: '45m',
		},
    }
};

function GetAnalysis (attempts, URL, endpoint_note, tag_note,) {
    let query;
	let attempt = 1;
    // Give service time to complete an analysis.
    while (attempt <= attempts) {
        query = http.get(URL);
        try {
            if (query.status == 200 && query.json().result != 'pending') {
                if (check(query, { "analysis correct": (q) => q.json().result == "covid" })) {
                    analysisCorrect.add(1, { endpoint: endpoint_note, tag: tag_note });
                } else {
                    errors.add(1, { endpoint: endpoint_note, tag: tag_note });
                }
                return;
            }
        } catch (e) {
            console.error("Failed to parse GET /analysis response");
            errors.add(1, { endpoint: endpoint_note, tag: tag_note });
            return;
        }

        attempt += 1;
        sleep(10);
    }
    
    // Final check to determine if the analysis has succeeded or not.
    // Needed so that only a single check is performed on the analysis results.
    // Logic only gets here if a check is not performed in the while attempts loop.
    try {
        if (check(query, { 
                            "analysis result status 200": (q) => q.status === 200, 
                            "analysis correct": (q) => q.json().result == "covid" 
                         })) {
            analysisCorrect.add(1, { endpoint: endpoint_note, tag: tag_note });
        } else {
            errors.add(1, { endpoint: endpoint_note, tag: tag_note });
        }
    } catch (e) {
        console.error("Failed to parse GET /analysis response")
        errors.add(1, { endpoint: endpoint_note, tag: tag_note });
        return;
    }
}

function LabResults (ids, URL, endpoint_note, tag_note) {
    let query = http.get(URL);
    try {
        check(query, {
            'is status 200': (r) => r.status === 200,
        });
        const queryResults = query.json();
        const allValidResults = queryResults.every(
            (entry) => entry.result === "pending" || entry.result === "covid"
        );
        check(null, {
            'all results valid (pending/covid)': () => allValidResults,
        });
        if (!allValidResults) {
            errors.add(1, {
                endpoint: endpoint_note,
                tag: tag_note,
            });
        }
    } catch (e) {
        console.error("Failed to parse JSON from GET /labs/results", e);
        errors.add(1, {
            endpoint: endpoint_note,
            tag: tag_note,
        });
    }
}

/**
 * Normal Circumstances - easy. 
 * Low load and gentle increase in load.
 * Only 5% of the analysis requests are urgent.
 * 25% of the analysis requests are queried for the result. - GET
 */
export function Normal_Circumstance() {
	attempted.add(1, { tag: "normal circumstances" });

    let isUrgent = Math.random() < 0.05;
    let postURL = `${ENDPOINT}/api/v1/analysis?patient_id=36295831522&lab_id=QML40671&urgent=${isUrgent}`;
    let response = http.post(postURL, JSON.stringify({ "image": covid1 }), params);
    check(response, {
        'analysis request status 201': (r) => r.status === 201,
    });
    let taskId;
    try {
        const data = response.json();
        taskId = data.id;
    } catch (e) {
        console.error("Failed to parse POST response or extract task ID");
		errors.add(1, { endpoint: "POST /analysis", tag: "normal circumstances" });
        return;
    }
    
    // Check 25% of the results.
    if (Math.random() < 0.25 && taskId) {
        let resultURL = `${ENDPOINT}/api/v1/analysis?request_id=${taskId}`
		let attempts = 6;  // One minute to complete analysis under low load.
		GetAnalysis(attempts, resultURL, "GET /analysis", "normal circumstances")
	}
    sleep(10);
}

/**
 * Curiosity Killed the Server. 
 * Start with 20 or so analysis requests to populate some data in their database. 
 * Slowly ramp up simple test result queries to a high load
 * Keep it at a high load for 3 to 5 minutes.
 * Queries:  
 * a lot of (GET /analysis).
 * a few queries patient results (GET /patients/results).
 * a small number for lab results (GET /labs/results).
 */
 export function Curiosity_Killed() {
    attempted.add(1, { tag: "curiosity killed" });
    // Phase 1: Populate DB with ~20 analysis requests.
    if (__ITER < 2) { // Each VU runs the function multiple times, only populate once.
        let isUrgent = Math.random() < 0.5;
        let postURL = `${ENDPOINT}/api/v1/analysis?patient_id=36295831522&lab_id=QML41203&urgent=${isUrgent}`;
        let response = http.post(postURL, JSON.stringify({"image": covid1}), params);
        check(response, {
            'is status 201': (r) => r.status === 201,
        });
        let taskId;
        try {
            const data = response.json();
            taskId = data.id; 
        } catch (e) {
            console.error("Failed to parse POST response or extract task ID");
            errors.add(1, { endpoint: "POST /analysis", tag: "curiosity killed" });
            return;
        }

		// Check results of most analysis requests.
        if (Math.random() < 0.9 && taskId) {
            let resultURL = `${ENDPOINT}/api/v1/analysis?request_id=${taskId}`
            let attempts = 12;  // Two minutes to complete analysis.
            GetAnalysis(attempts, resultURL, "GET /analysis", "curiosity killed")
        }
    }
	// Other significant queries.
    let prop = Math.random();
    if (prop < 0.2) {
        let getURL = `${ENDPOINT}/api/v1/labs/results/QML40671`;
        LabResults ("", getURL, "GET /labs/results", "invalid JSON")
    } else if (prop < 1) {
        let getURL = `${ENDPOINT}/api/v1/patients/results?patient_id=36295831522`
        LabResults ("", getURL, "GET /patients/results", "invalid JSON")
    }
    sleep(5);
}

/**
 * Epidemic Early Stages. 
 * Slowly ramp up analysis requests to a high load and keep it at a high load for 3 to 5 minutes. 
 * Have about 15% of the requests as being urgent. 
 * Have some requests querying for batches of results, DO NOT make this too high of a load.
 */
export function Epidemic_Early() {
    attempted.add(1, { tag: "epidemic early" });
    let isUrgent = Math.random() < 0.15;
    let postURL = `${ENDPOINT}/api/v1/analysis?patient_id=12345678911&lab_id=ACL42151&urgent=${isUrgent}`;
    let response = http.post(postURL, JSON.stringify({ "image": covid1 }), params);
    check(response, {
        'early epidemic POST status 201': (r) => r.status === 201,
    });
    let taskId;
    try {
        const data = response.json();
        taskId = data.id; 
    } catch (e) {
        console.error("Failed to parse POST response or extract task ID");
        errors.add(1, { endpoint: "POST /analysis", tag: "epidemic early" });
        return;
    }

    let prop = Math.random()
    // Check analysis processing 25% of the time.
    if (prop < 0.25) {
        let resultURL = `${ENDPOINT}/api/v1/analysis?request_id=${taskId}`
        let attempts = 12;  // Two minutes to complete analysis.
        GetAnalysis(attempts, resultURL, "GET /analysis", "epidemic early")
    }
	// Perform lab results query with parameters 20% of the time.
    if (prop > 0.8) {
        let getURL = `${ENDPOINT}/api/v1/labs/results/QML41203?urgent=true&status=covid`
        let queries = http.get(getURL);
        check(queries, {
            'early epidemic GET status 200': (r) => r.status === 200,
            'all results have urgent=true and result=covid': (r) => { 
                try {
					const data = r.json();
					return Array.isArray(data) && data.every(item => item.urgent === true
						&& item.result === 'covid'
						&& item.lab_id === 'QML41203');
                } catch (e) {
                    console.error('Failed to parse JSON response:', e);
                    return false;
                }
            }
        });
	// Otherwise perform lab query for all results.
	} else {
        let getURL = `${ENDPOINT}/api/v1/labs/results/ACL42151`
        LabResults("", getURL, "GET /labs/results", "invalid JSON")
    }

    sleep(2); // Shorter sleep for increased load
}

/**
 * Have a test related to Epidemic Peak.
 * Slowly ramp up analysis requests to a high load.
 * Have about 20% of the requests as being urgent.
 * Slowly ramp up a couple of different query requests in parallel with the analysis requests.
 * Run both at a high load for 3 to 5 minutes.
 */
export function Epidemic_Peak() {
    attempted.add(1, { tag: "epidemic peak" });
    const isUrgent = Math.random() < 0.2;
    let postURL = `${ENDPOINT}/api/v1/analysis?patient_id=12345678911&lab_id=ACL42151&urgent=${isUrgent}`;
    let response = http.post(postURL, JSON.stringify({ "image": covid1 }), params);
    check(response, {
        'peak POST status 201': (r) => r.status === 201,
    });
    let taskId;
    try {
        const data = response.json();
        taskId = data.id; 
    } catch (e) {
        console.error("Failed to parse POST response or extract task ID");
        errors.add(1, { endpoint: "POST /analysis", tag: "epidemic peak" });
        return;
    }

    let prop = Math.random()
	// Perform lab results query with parameters 10% of the time.
    if (prop < 0.1) {
        let getURL = `${ENDPOINT}/api/v1/labs/results/QML41203?urgent=false&status=covid`
        let labResult = http.get(getURL);
        check(labResult, {
            'peak epidemic GET status 200': (r) => r.status === 200,
            'all results have urgent=false and result=covid': (r) => { 
                try {
                    const data = r.json();
                    return Array.isArray(data) && data.every(
                        item => item.urgent === false 
                        && item.result === 'covid' 
                        && item.lab_id === 'QML41203' 
                    );
                } catch (e) {
                    console.error('Failed to parse JSON response:', e);
                    return false;
                }
            }
        });
	// Other 10% of the time query all results for a lab.
    } else if (prop < 0.2) {
        let getURL = `${ENDPOINT}/api/v1/labs/results/ACL42151`
        LabResults ("", getURL, "GET /labs/results", "invalid JSON")
    }
	// Check lab summary 25% of the time.
    if (prop > 0.75) {
        let getURL = `${ENDPOINT}/api/v1/labs/results/ACL42151/summary`
        let labSummary = http.get(getURL);
        check(labSummary, {
            'peak epidemic GET status 200': (r) => r.status === 200,
        });
		try {
			let summary = labSummary.json();
			let pending = summary.pending || 0;
			let covid = summary.covid || 0;
			let h5n1 = summary.h5n1 || 0;
			let healthy = summary.healthy || 0;
			let failed = summary.failed || 0;
			check(null, {
				'only pending or covid results': () => (pending + covid) > 0 && (h5n1 + healthy + failed) == 0
			});
		} catch (e) {
			console.error("Failed to parse POST response or extract task ID");
			errors.add(1, { endpoint: "POST labs/results/summary", tag: "epidemic peak" });
			return;
		}
    }
	// Check analysis results 50% of the time.
    if (prop < 0.5 && taskId) {
        let resultURL = `${ENDPOINT}/api/v1/analysis?request_id=${taskId}`
        let attempts = 18;    // Three minutes to complete analysis.
        GetAnalysis(attempts, resultURL, "GET /analysis", "epidemic peak")
	// Move analysis job to another lab 10% of the time.
    } else if (prop < 0.6 && taskId) {
        let putURL = `${ENDPOINT}/api/v1/analysis?request_id=${taskId}&lab_id=QML41203`
        let putResult = http.put(putURL);
        check(putResult, {
            'peak epidemic GET status 200': (r) => r.status === 200,
        });
        let getRequestURL = `${ENDPOINT}/api/v1/analysis?request_id=${taskId}`
		const queryResults = http.get(getRequestURL);
        try {
            const queryData = queryResults.json();
            check(queryData, {
				'peak epidemic GET status 200': (r) => r.status === 200,
                'Validate data': (r) => r.request_id === taskId && r.lab_id === "QML41203"
            });
        } catch (e) {
            console.error("Failed to parse JSON from GET /analysis", e);
            errors.add(1, {
                endpoint: "GET /analysis",
                tag: "epidemic peak",
            });
        }
    }
    sleep(1); // Shorter sleep for increased load
}

/**
 * Provide a more extended cool down period to give longer to finish analysis request processing.
 */
export function Cool_Down () {
	sleep(15)
	return;
}