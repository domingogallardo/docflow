-- bump-simple: mtime := (ahora + 100 años) + i s
on run {input, parameters}
	set baseEpoch to do shell script "/bin/date -v+100y +%s"
	set counter to 0
	repeat with aFile in input
		set counter to counter + 1
		set p to POSIX path of (aFile as alias)
		set ts to do shell script "/bin/sh -c " & quoted form of ("date -j -r $(( " & baseEpoch & " + " & counter & " )) +%Y%m%d%H%M.%S")
		do shell script "/usr/bin/touch -mt " & ts & space & quoted form of p
	end repeat
end run