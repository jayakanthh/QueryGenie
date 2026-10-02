# Demo rehearsal (research/demo_check.py)

Every demo question asked through the app (CodeS-1B, Balanced, no context) and compared with a hand-written correct query.

| # | Question | Shows | Queries agree | Result |
|---|---|---|---|---|
| 1 | List the subjects and the average marks for each subject. | confident answer + bar chart | 4 of 4 | ✅ correct |
| 2 | What are the names of the students in the CSE department? | finds the stored value 'CSE' | 4 of 4 | ✅ correct |
| 3 | Which student scored the highest marks in DBMS? | join across two tables | 4 of 4 | ✅ correct |
| 4 | Show the name and average marks of every student. | join + group by + chart | 4 of 4 | ✅ correct |
| 5 | How many students are there in each department? | 3 of 4 agree + chart | 3 of 4 | ✅ correct |
| 6 | Who topped each subject? | the enhancement: queries disagree, it asks | 1 of 4 | ✅ asks (correct behaviour) |
| 7 | show me all | vague: asks 'All of what?' | 2 of 4 | ✅ asks (correct behaviour) |
