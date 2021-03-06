#!/usr/bin/env python

import datetime
import json

from flask import Flask
from flask import render_template, request

import cms_settings as settings
from models import Race, Candidate, State
import output as o

app = Flask(__name__)


@app.route('/timemachine/', methods=['GET', 'POST'])
@app.route('/timemachine/<filename>', methods=['GET'])
def timemachine_file(filename=None):

    if request.method == 'GET':
        file_times = []
        if filename == None:
            hours = [(14, range(30, 60)), (15, range(0, 30))]
            for hour, minutes in hours:
                for minute in minutes:
                    file_times.append({
                            'name': '%s-%s' % (hour, minute),
                            'hour': int(hour) - 12,
                            'minute': str(minute).zfill(2)
                        })

            try:
                with open('timemachine/config.json', 'r') as j:
                    data = json.loads(j.read())
                    current_time = data['time']
            except IOError:
                current_time = '0-0'

            context = {
                'file_times': file_times,
                'current_time': current_time,
                'settings': settings
            }
            return render_template('time_machine.html', **context)

        else:
            with open('www/timemachine/%s' % filename, 'r') as f:
                return f.read()

    if request.method == 'POST':
        file_time = request.form.get('file_time', None)

        if file_time == None:
            return 'BORK'

        else:
            for file_name in ['US', 'ME_D', 'NE_D']:
                file_path = u'%s_%s' % (file_name, file_time)
                with open('test_data/timemachine/%s.txt' % file_path, 'r') as f:
                    file_data = f.read()

                with open('www/timemachine/%s.txt' % file_name, 'w') as w:
                    w.write(file_data)

            with open('www/timemachine/config.json', 'w') as c:
                data = {}
                data['time'] = file_time
                c.write(json.dumps(data))

            return 'WIN'


@app.route('/races/president/', methods=['GET', 'POST'])
@app.route('/races/president/<featured>/', methods=['GET', 'POST'])
def president(featured=None):
    """
    Read/update list of presidential state winners.
    """

    is_featured = False
    if featured == 'featured':
        is_featured = True

    if request.method == 'GET':

        states = State.select().order_by(State.name.asc())

        if is_featured == True:
            states = states.where(State.prediction == 't').order_by(State.name.asc())

        context = {
            'states': states,
            'settings': settings
        }

        return render_template('president.html', **context)

    if request.method == 'POST':
        # First, try and get the state.
        race_slug = request.form.get('race_slug', None)
        race_slug = race_slug.strip()

        # Next, try to get the AP call.
        accept_ap_call = request.form.get('accept_ap_call', None)

        if accept_ap_call != None:
            # Figure out which direction we're going and send an appropriate message.
            if accept_ap_call.lower() == 'true':
                accept_ap_call = True
            else:
                accept_ap_call = False

        # Accumulate changes so we only execute a single update
        update_dict = {}

        # If all the pieces are here, do something.
        if race_slug != None and accept_ap_call != None:

            # Run some SQL to change the status of this set of candidate's accept_ap_call column.
            sq = State.update(accept_ap_call=accept_ap_call).where(State.id == race_slug)
            sq.execute()

            # Clear the NPR winner status of candidates who we accept AP calls for.
            if accept_ap_call == True:
                update_dict['npr_call'] = 'n',
                update_dict['npr_called_at'] = None

        # Try and get the winner.
        party = request.form.get('party', None)

        # Try and get a clear_all.
        clear_all = request.form.get('clear_all', None)

        if race_slug != None and clear_all != None:
            # If we're passing clear_all as true ...
            if clear_all == 'true':
                update_dict['npr_call'] = 'n',
                update_dict['npr_called_at'] = None

        # If all of the pieces are here, do something.
        if race_slug != None and party != None:
            update_dict['npr_call'] = party,
            update_dict['npr_called_at'] = datetime.datetime.utcnow()

        if update_dict:
            uq = State.update(**update_dict).where(State.id == race_slug)
            uq.execute()

        if settings.DEBUG:
            o.write_electris_json()
            o.write_president_json()
            o.write_bop_json()

        # TODO
        # Return a 200. This is probably bad.
        # Need to figure out what should go here.
        return "Success."


@app.route('/races/<house>/', methods=['GET', 'POST'])
@app.route('/races/<house>/<featured>/', methods=['GET', 'POST'])
def house(house, featured=None):
    """
    Read/update list of house candidates.
    """

    house_slug = u'H'
    if house == 'senate':
        house_slug = u'S'

    is_featured = False
    if featured == u'featured':
        is_featured = True

    if request.method == 'GET':

        # Get all of the candidates that match this race which are either
        # Republicans or Democrats or have the first name Angus or Bernie and
        # we ignore the Democrat in the Maine race.
        candidates = Candidate\
            .select()\
            .join(Race)\
            .where(
                Race.office_code == house_slug,
                (Candidate.party == 'Dem') | (Candidate.party == 'GOP') | (Candidate.first_name == 'Angus') | (Candidate.first_name == 'Bernie'),
                Candidate.last_name != 'Dill')

        if is_featured:
            candidates = candidates.where(Race.featured_race == True)

        candidates = candidates.order_by(
                Race.state_postal.desc(),
                Race.district_id.asc(),
                Candidate.party.asc())

        race_count = Race.select().where(Race.office_code == house_slug)

        if is_featured:
            race_count = race_count.where(Race.featured_race == True)

        context = {
            'candidates': candidates,
            'count': race_count.count(),
            'house': house,
            'settings': settings
        }

        return render_template('house_senate.html', **context)

    # Alternately, what if someone is POSTing?
    if request.method == 'POST':

        # Everything needs a race slug.
        race_slug = request.form.get('race_slug', None)
        race = Race.select().where(Race.slug == race_slug).get()

        # 1.) Perhaps we're trying to set the accept_ap_call flag on some races?
        accept_ap_call = request.form.get('accept_ap_call', None)

        if accept_ap_call != None:
            if accept_ap_call.lower() == 'true':
                accept_ap_call = True
            else:
                accept_ap_call = False

        if race_slug != None and accept_ap_call != None:
            aq = Race.update(accept_ap_call=accept_ap_call).where(Race.slug == race.slug)
            aq.execute()

            if accept_ap_call == True:
                rq = Candidate.update(npr_winner=False).where(Candidate.race == race)
                rq.execute()

        # 2.) Perhaps we're trying to set an NPR winner?
        first_name = request.form.get('first_name', None)
        last_name = request.form.get('last_name', None)
        clear_all = request.form.get('clear_all', None)

        if race_slug != None and clear_all != None:
            if clear_all == 'true':
                rq = Candidate.update(npr_winner=False).where(Candidate.race == race)
                rq.execute()

                rq2 = Race.update(npr_called=False).where(Race.slug == race_slug)
                rq2.execute()

        if race_slug != None and first_name != None and last_name != None:

            rq = Candidate.update(npr_winner=False).where(Candidate.race == race)
            rq.execute()

            cq = Candidate.update(npr_winner=True).where(
                Candidate.race == race,
                Candidate.first_name == first_name,
                Candidate.last_name == last_name)
            cq.execute()

            race_update = {}
            race_update['npr_called'] = True
            if race.accept_ap_call == False:
                if race.npr_called_time == None:
                    race_update['npr_called_time'] = datetime.datetime.utcnow()

            rq2 = Race.update(**race_update).where(Race.slug == race_slug)
            rq2.execute()

        # 3.) Perhaps we're trying to set this as a featured race?
        featured_race = request.form.get('featured_race', None)
        if featured_race:
            if featured_race.lower() == 'true':
                featured_race = True
            else:
                featured_race = False

        if race_slug != None and featured_race != None:
            fq = Race.update(featured_race=featured_race).where(Race.slug == race_slug)
            print fq.execute()

        if settings.DEBUG:
            o.write_house_json()
            o.write_senate_json()
            o.write_bop_json()

        # TODO
        # Return a 200. This is probably bad.
        # Need to figure out what should go here.
        return "Success."


if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=settings.DEBUG)
