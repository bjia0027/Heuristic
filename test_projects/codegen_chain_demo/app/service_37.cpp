#include "service_37.h"

Service37::Service37() {}

void Service37::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service37::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
