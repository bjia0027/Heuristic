#include "service_12.h"

Service12::Service12() {}

void Service12::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service12::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
