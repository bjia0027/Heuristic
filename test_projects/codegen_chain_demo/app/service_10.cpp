#include "service_10.h"

Service10::Service10() {}

void Service10::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service10::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
