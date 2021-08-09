#!/bin/bash

WORKDIR=$PWD
CONFIGS=$WORKDIR/bots/enabled/*.yaml
PIDDIR=$WORKDIR/bots/run

cd $WORKDIR
source ./venv/bin/activate

keep_bots_up(){
	while : 
	do

		for C in $CONFIGS
		do
			BOTNAME=${C##*/}
			BOTNAME=${BOTNAME%.*}

			PIDFILE=$PIDDIR/$BOTNAME.PID
			#echo $BOTNAME
			if ! ps -p $(cat $PIDFILE) > /dev/null 2>&1; then
				echo "Bot $BOTNAME died!"
				#python dummy.py &
				nohup python telegram_music_bot.py "$C" &
				echo $! > $PIDFILE

			fi	
		done
		sleep 5
	done

}

for C in $CONFIGS
do

	BOTNAME=${C##*/}
	BOTNAME=${BOTNAME%.*}

	PIDFILE=$PIDDIR/$BOTNAME.PID
	if [ -f $PIDFILE ]; then
		echo "Seems line $BOTNAME already running. Killing $(cat $PIDFILE).."
		kill $(cat $PIDFILE)
	fi

	#python dummy.py &
	nohup python telegram_music_bot.py "$C" &
	echo $! > $PIDFILE
done


keep_bots_up
